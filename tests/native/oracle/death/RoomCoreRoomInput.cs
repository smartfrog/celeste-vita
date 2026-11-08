using System.IO;
using System.Text.Json;
using Celeste;

namespace DeathOracle;

static class RoomCoreRoomInput
{
    public static BinaryPacker.Element ReadElement(JsonElement input)
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
}
