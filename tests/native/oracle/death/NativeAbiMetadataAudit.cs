using System;
using System.Collections.Generic;
using System.Collections.Immutable;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;

namespace DeathOracle;

static class NativeAbiMetadataAudit
{
    static readonly string[] RootTypes = {
        "FMOD.ADVANCEDSETTINGS", "FMOD.SYSTEM_CALLBACK", "FMOD.SYSTEM_CALLBACK_TYPE", "FMOD.DSP_RESAMPLER"
    };
    static readonly string[] ExpectedRootTypes = { "FMOD.ADVANCEDSETTINGS", "FMOD.SYSTEM_CALLBACK", "FMOD.SYSTEM_CALLBACK_TYPE" };
    static readonly string[] WrongStudioTypes = { "FMOD.Studio.ADVANCEDSETTINGS", "FMOD.Studio.SYSTEM_CALLBACK", "FMOD.Studio.SYSTEM_CALLBACK_TYPE" };
    static readonly string[] NativeCalls = {
        "FMOD.System::FMOD_System_SetAdvancedSettings",
        "FMOD.System::FMOD_System_GetAdvancedSettings",
        "FMOD.System::FMOD_System_SetCallback"
    };

    sealed class Types : ISignatureTypeProvider<string, object>
    {
        public static string Name(MetadataReader reader, TypeDefinitionHandle handle)
        {
            var type = reader.GetTypeDefinition(handle);
            return type.GetDeclaringType().IsNil
                ? reader.GetString(type.Namespace) + "." + reader.GetString(type.Name)
                : Name(reader, type.GetDeclaringType()) + "+" + reader.GetString(type.Name);
        }

        public string GetTypeFromDefinition(MetadataReader reader, TypeDefinitionHandle handle, byte rawTypeKind) => Name(reader, handle);

        public string GetTypeFromReference(MetadataReader reader, TypeReferenceHandle handle, byte rawTypeKind)
        {
            var type = reader.GetTypeReference(handle);
            return type.ResolutionScope.Kind == HandleKind.TypeReference
                ? GetTypeFromReference(reader, (TypeReferenceHandle)type.ResolutionScope, rawTypeKind) + "+" + reader.GetString(type.Name)
                : reader.GetString(type.Namespace) + "." + reader.GetString(type.Name);
        }

        public string GetTypeFromSpecification(MetadataReader reader, object genericContext, TypeSpecificationHandle handle, byte rawTypeKind) =>
            reader.GetTypeSpecification(handle).DecodeSignature(this, genericContext);

        public string GetPrimitiveType(PrimitiveTypeCode code) => code.ToString();
        public string GetSZArrayType(string elementType) => elementType + "[]";
        public string GetArrayType(string elementType, ArrayShape shape) =>
            elementType + "[" + shape.Rank + ";" + string.Join(",", shape.Sizes) + ";" + string.Join(",", shape.LowerBounds) + "]";
        public string GetByReferenceType(string elementType) => elementType + "&";
        public string GetPointerType(string elementType) => elementType + "*";
        public string GetPinnedType(string elementType) => elementType + " pinned";
        public string GetModifiedType(string modifier, string unmodifiedType, bool isRequired) =>
            unmodifiedType + (isRequired ? " modreq(" : " modopt(") + modifier + ")";
        public string GetGenericInstantiation(string genericType, ImmutableArray<string> typeArguments) =>
            genericType + "<" + string.Join(",", typeArguments) + ">";
        public string GetGenericMethodParameter(object genericContext, int index) => "!!" + index;
        public string GetGenericTypeParameter(object genericContext, int index) => "!" + index;
        public string GetFunctionPointerType(MethodSignature<string> signature) => Signature(signature);

        public static string Signature(MethodSignature<string> signature) =>
            signature.Header.RawValue + ":" + signature.GenericParameterCount + ":" + signature.RequiredParameterCount +
            ":" + signature.ReturnType + "(" + string.Join(",", signature.ParameterTypes) + ")";
    }

    static string Bytes(MetadataReader reader, BlobHandle blob) =>
        blob.IsNil ? "" : Convert.ToHexString(reader.GetBlobBytes(blob));

    static Dictionary<string, string> ReadImports(string path)
    {
        using var stream = File.OpenRead(path);
        using var pe = new PEReader(stream);
        var reader = pe.GetMetadataReader();
        var result = new Dictionary<string, string>();
        foreach (var typeHandle in reader.TypeDefinitions)
            foreach (var methodHandle in reader.GetTypeDefinition(typeHandle).GetMethods())
            {
                var method = reader.GetMethodDefinition(methodHandle);
                if ((method.Attributes & MethodAttributes.PinvokeImpl) == 0) continue;
                var import = method.GetImport();
                var key = Types.Name(reader, typeHandle) + "::" + reader.GetString(method.Name) + ":" +
                    Types.Signature(method.DecodeSignature(new Types(), null));
                var value = new
                {
                    Attributes = (int)method.Attributes, Implementation = (int)method.ImplAttributes,
                    importFlags = (int)import.Attributes,
                    Library = reader.GetString(reader.GetModuleReference(import.Module).Name),
                    EntryPoint = reader.GetString(import.Name),
                    noManagedBody = method.RelativeVirtualAddress == 0,
                    Parameters = method.GetParameters().Select(handle => reader.GetParameter(handle)).Select(parameter => new
                    {
                        parameter.SequenceNumber, Attributes = (int)parameter.Attributes, Name = reader.GetString(parameter.Name),
                        Marshal = Bytes(reader, parameter.GetMarshallingDescriptor()),
                        Default = parameter.GetDefaultValue().IsNil ? "" :
                            reader.GetConstant(parameter.GetDefaultValue()).TypeCode + ":" + Bytes(reader, reader.GetConstant(parameter.GetDefaultValue()).Value)
                    }).ToArray()
                };
                result.Add(key, JsonSerializer.Serialize(value));
            }
        return result;
    }

    static string Name(MetadataReader reader, EntityHandle handle) => handle.Kind switch
    {
        HandleKind.TypeDefinition => Types.Name(reader, (TypeDefinitionHandle)handle),
        HandleKind.TypeReference => new Types().GetTypeFromReference(reader, (TypeReferenceHandle)handle, 0),
        HandleKind.TypeSpecification => new Types().GetTypeFromSpecification(reader, null, (TypeSpecificationHandle)handle, 0),
        _ => throw new InvalidDataException("Unsupported type handle: " + handle.Kind)
    };

    static string[] AttributeNames(MetadataReader reader, CustomAttributeHandleCollection handles)
    {
        var names = new List<string>();
        foreach (var handle in handles)
        {
            var attribute = reader.GetCustomAttribute(handle);
            var constructor = attribute.Constructor;
            if (constructor.Kind == HandleKind.MethodDefinition)
                names.Add(Types.Name(reader, reader.GetMethodDefinition((MethodDefinitionHandle)constructor).GetDeclaringType()));
            else if (constructor.Kind == HandleKind.MemberReference)
            {
                var member = reader.GetMemberReference((MemberReferenceHandle)constructor);
                names.Add(Name(reader, member.Parent));
            }
            else throw new InvalidDataException("Unsupported custom attribute constructor: " + constructor.Kind);
        }
        names.Sort(StringComparer.Ordinal);
        return names.ToArray();
    }

    sealed record FieldContract(string Name, int Attributes, string Signature, int Offset, string Constant);
    sealed record TypeContract(string Name, bool Found, int Attributes, string BaseType, string Layout,
        FieldContract[] Fields, string[] AttributesPresent, string InvokeSignature, int InvokeAttributes);

    static TypeContract Contract(MetadataReader reader, string fullName)
    {
        foreach (var handle in reader.TypeDefinitions)
        {
            if (Types.Name(reader, handle) != fullName) continue;
            var type = reader.GetTypeDefinition(handle);
            var fields = type.GetFields().Select(fieldHandle =>
            {
                var field = reader.GetFieldDefinition(fieldHandle);
                string constant = field.GetDefaultValue().IsNil ? "" :
                    reader.GetConstant(field.GetDefaultValue()).TypeCode + ":" + Bytes(reader, reader.GetConstant(field.GetDefaultValue()).Value);
                return new FieldContract(reader.GetString(field.Name), (int)field.Attributes,
                    field.DecodeSignature(new Types(), null), field.GetOffset(), constant);
            }).ToArray();
            var methods = type.GetMethods().Select(methodHandle => reader.GetMethodDefinition(methodHandle)).ToArray();
            MethodDefinition? invoke = methods.Cast<MethodDefinition?>().FirstOrDefault(method => reader.GetString(method.Value.Name) == "Invoke");
            var layout = type.GetLayout();
            return new TypeContract(fullName, true, (int)type.Attributes,
                type.BaseType.IsNil ? "" : Name(reader, type.BaseType),
                layout.IsDefault ? "default" : layout.PackingSize + ":" + layout.Size,
                fields, AttributeNames(reader, type.GetCustomAttributes()),
                invoke.HasValue ? Types.Signature(invoke.Value.DecodeSignature(new Types(), null)) : "",
                invoke.HasValue ? (int)invoke.Value.Attributes : 0);
        }
        return new TypeContract(fullName, false, 0, "", "", Array.Empty<FieldContract>(), Array.Empty<string>(), "", 0);
    }

    static string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

    static (TypeContract Generated, TypeContract Original, bool Ok, string[] Missing) CompareContract(string generated, string original, string fullName)
    {
        using var generatedStream = File.OpenRead(generated);
        using var generatedPe = new PEReader(generatedStream);
        var generatedContract = Contract(generatedPe.GetMetadataReader(), fullName);
        using var originalStream = File.OpenRead(original);
        using var originalPe = new PEReader(originalStream);
        var originalContract = Contract(originalPe.GetMetadataReader(), fullName);
        var missing = new List<string>();
        if (!generatedContract.Found) missing.Add("generated");
        if (!originalContract.Found) missing.Add("original");
        var ok = generatedContract.Found && originalContract.Found &&
            JsonSerializer.Serialize(generatedContract) == JsonSerializer.Serialize(originalContract);
        return (generatedContract, originalContract, ok, missing.ToArray());
    }

    public static void Run(string[] args)
    {
        if (args.Length != 6) throw new ArgumentException("Expected native-abi-metadata-audit <generated> <output> <celeste> <fna> <expected-generated-count>");
        string generatedPath = Path.GetFullPath(args[1]);
        string outputPath = Path.GetFullPath(args[2]);
        string celestePath = Path.GetFullPath(args[3]);
        string fnaPath = Path.GetFullPath(args[4]);
        int expectedGenerated = int.Parse(args[5]);

        var originals = ReadImports(celestePath).Concat(ReadImports(fnaPath))
            .ToDictionary(entry => entry.Key, entry => entry.Value, StringComparer.Ordinal);
        var generated = ReadImports(generatedPath);
        var failures = generated.Where(entry => !originals.TryGetValue(entry.Key, out var value) || value != entry.Value)
            .Select(entry => new
            {
                key = entry.Key, generated = entry.Value, original = originals.GetValueOrDefault(entry.Key),
                originalSameMethod = originals.Where(candidate => candidate.Key.StartsWith(
                    entry.Key[..entry.Key.IndexOf(':', entry.Key.IndexOf("::", StringComparison.Ordinal) + 2)] + ":",
                    StringComparison.Ordinal)).ToArray()
            }).ToArray();

        var contracts = RootTypes.Select(name => {
            var comparison = CompareContract(generatedPath, celestePath, name);
            return new { name, generated = comparison.Generated, original = comparison.Original, ok = comparison.Ok, missing = comparison.Missing };
        }).ToArray();

        var nativeCallEvidence = NativeCalls.Select(prefix => new {
            name = prefix,
            generated = generated.Where(entry => entry.Key.StartsWith(prefix + ":", StringComparison.Ordinal)).Select(entry => entry.Key).ToArray(),
            original = originals.Where(entry => entry.Key.StartsWith(prefix + ":", StringComparison.Ordinal)).Select(entry => entry.Key).ToArray()
        }).ToArray();

        var result = new
        {
            generatedAssembly = generatedPath,
            generatedAssemblySha256 = Hash(generatedPath),
            generatedNativeImports = generated.Count,
            expectedGeneratedNativeImports = expectedGenerated,
            originalNativeImports = originals.Count,
            allGeneratedNativeBodiesNull = generated.Values.All(value =>
                JsonDocument.Parse(value).RootElement.GetProperty("noManagedBody").GetBoolean()),
            normalization = "Compare type/method/qualified-signature and native import metadata; assembly name is ignored. No FMOD.Studio/root collapse.",
            expectedRootTypes = ExpectedRootTypes,
            wrongStudioTypes = WrongStudioTypes,
            studioTypeReferences = generated.Keys.Where(key => WrongStudioTypes.Any(name => key.Contains(name, StringComparison.Ordinal))).ToArray(),
            nativeCalls = NativeCalls,
            nativeCallEvidence,
            rootContracts = contracts,
            failures,
            originals = new[] {
                new { path = celestePath, sha256 = Hash(celestePath), imports = ReadImports(celestePath).Count },
                new { path = fnaPath, sha256 = Hash(fnaPath), imports = ReadImports(fnaPath).Count }
            }
        };
        File.WriteAllText(outputPath, JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }) + "\n");
        Console.WriteLine(JsonSerializer.Serialize(new { result.generatedNativeImports, result.originalNativeImports,
            result.allGeneratedNativeBodiesNull, failures = failures.Length, rootFailures = contracts.Count(contract => !contract.ok),
            nativeCalls = nativeCallEvidence.Length }));
        Environment.Exit(generated.Count == expectedGenerated && failures.Length == 0 && contracts.All(contract => contract.ok) ? 0 : 1);
    }
}
