using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Celeste;
using Microsoft.Xna.Framework;
using Monocle;

namespace Microsoft.Xna.Framework
{
    public struct Point { public int X, Y; }
}

namespace Celeste
{
    public sealed class AreaData
    {
        public static List<AreaData> Areas = new();
        public bool Interlude;
    }
    public sealed class FixtureSession
    {
        public AreaKey Area = new(1);
        public string Level = "1", FurthestSeenLevel = "1";
        public int Deaths;
    }
    public sealed class Strawberry
    {
        public Strawberry(EntityData data, Vector2 offset, EntityID id) => throw new InvalidOperationException("Excluded golden constructor reached");
    }
    public sealed class ClutterBlock : Entity
    {
        public enum Colors { }
        public bool TopSideOpen, LeftSideOpen, RightSideOpen, OnTheGround;
        public HashSet<ClutterBlock> HasBelow = new();
        public List<ClutterBlock> Above = new(), Below = new();
        public ClutterBlock(Vector2 position, MTexture texture, Colors color) => throw new InvalidOperationException("Excluded initialized clutter reached");
    }
    public partial class GoldenBranch
    {
        public FixtureSession Session = new();
        public void Add(Strawberry berry) => throw new InvalidOperationException("Excluded golden addition reached");
    }
}

static class RoomCoreHelpers
{
    static BinaryPacker.Element ReadElement(JsonElement input)
    {
        var element = new BinaryPacker.Element { Name = input.GetProperty("name").GetString(), Attributes = new(), Children = new() };
        foreach (var attribute in input.GetProperty("attributes").EnumerateObject())
            element.Attributes.Add(attribute.Name, attribute.Value.ValueKind switch {
                JsonValueKind.String => attribute.Value.GetString(),
                JsonValueKind.True => true,
                JsonValueKind.False => false,
                JsonValueKind.Number => attribute.Value.TryGetInt32(out var integer) ? (object)integer : attribute.Value.GetSingle(),
                _ => throw new InvalidDataException("Unsupported raw map scalar") });
        foreach (var child in input.GetProperty("children").EnumerateArray()) element.Children.Add(ReadElement(child));
        return element;
    }

    static void Main(string[] args)
    {
        AreaData.Areas = new() { new AreaData(), new AreaData() };
        SaveData.Instance = new SaveData();
        foreach (int id in Enumerable.Range(0, AreaData.Areas.Count)) SaveData.Instance.Areas.Add(new AreaStats(id));
        var save = SaveData.Instance;
        if (save.CheatMode || save.DebugMode || save.UnlockedModes != 1 || save.Assists.GameSpeed != 10 ||
            save.Assists.DashMode != Assists.DashModes.Normal || save.Areas[1].Modes.Length != 3 ||
            save.Areas.SelectMany(area => area.Modes).Any(mode => mode.Completed))
            throw new Exception("Original source-default save fixture mismatch");
        using var raw = JsonDocument.Parse(File.ReadAllText(args[0]));
        using var stripped = JsonDocument.Parse(File.ReadAllText(args[2]));
        var levelData = new LevelData(ReadElement(raw.RootElement));
        var strippedData = new LevelData(ReadElement(stripped.RootElement));
        if (levelData.LoadSeed != 49 || levelData.Bounds.Height != 180 || levelData.Spawns.Count != 1 ||
            levelData.Spawns[0] != new Vector2(19, 144) || levelData.Entities.Count != 6 || levelData.Triggers.Count != 0 ||
            !levelData.Entities.Select(entity => (entity.ID, entity.Name)).SequenceEqual(strippedData.Entities.Select(entity => (entity.ID, entity.Name))) ||
            strippedData.FgDecals.Count != 0 || strippedData.BgDecals.Count != 0 || strippedData.ObjTiles != "")
            throw new Exception("Original LevelData constructor/profile mismatch");
        var entity = levelData.Entities.Single(entity => entity.Name == "goldenBerry");
        var branch = new GoldenBranch();
        branch.Run(entity, Vector2.Zero, new EntityID("1", entity.ID));
        var random = new PresentationOracle.TracedRandom(0);
        var control = new PrivateRuntime.Random(0);
        Calc.Random = random;
        int first = random.Next();
        if (first != control.Next()) throw new Exception("Original Random control mismatch");
        Calc.PushRandom(levelData.LoadSeed);
        var scopedOwner = Calc.Random;
        var scopedControl = new PrivateRuntime.Random(levelData.LoadSeed);
        if (Calc.Random.Next() != scopedControl.Next()) throw new Exception("Original scoped seed mismatch");
        Calc.PushRandom(91);
        Calc.Random.Next();
        Calc.PopRandom();
        if (!ReferenceEquals(Calc.Random, scopedOwner) || Calc.Random.Next() != scopedControl.Next())
            throw new Exception("Nested scoped RNG did not restore its previous owner/sequence");
        Calc.PopRandom();
        if (!ReferenceEquals(Calc.Random, random) || random.Next() != control.Next())
            throw new Exception("Original scoped RNG did not restore the persistent object/sequence");
        var initialized = typeof(ClutterBlockGenerator).GetField("initialized", BindingFlags.NonPublic | BindingFlags.Static);
        if ((bool)initialized.GetValue(null)) throw new Exception("Clutter initial state is not source-default false");
        int calls = random.Calls;
        for (int cycle = 0; cycle < 3; cycle++) ClutterBlockGenerator.Generate();
        if (random.Calls != calls || (bool)initialized.GetValue(null) || random.Next() != control.Next())
            throw new Exception("Empty-profile Generate changed RNG or initialization");
        File.WriteAllText(args[1], JsonSerializer.Serialize(new {
            status = "source-helpers-executed-not-room-core-closed", defaultSaveFixture = true, actualUserSave = false,
            areaCount = save.Areas.Count, modesPerArea = save.Areas[1].Modes.Length, unlockedModes = save.UnlockedModes,
            rawGoldenEntityId = entity.ID, sourceDerivedRoomLoadSeed = levelData.LoadSeed, nestedDiagnosticSeed = 91,
            rawFgDecals = levelData.FgDecals.Count, rawBgDecals = levelData.BgDecals.Count, rawObjTilesEmpty = levelData.ObjTiles == "",
            strippedFgDecals = strippedData.FgDecals.Count, strippedBgDecals = strippedData.BgDecals.Count,
            diagnosticSeed = 0, originalStartupRngParity = false, persistentRngRestored = true, clutterGenerateCalls = 3,
            coherentLifecycleClosure = false, completedLifecycleFamilies = 0
        }));
    }
}
