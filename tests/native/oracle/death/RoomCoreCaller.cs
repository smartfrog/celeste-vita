using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text.Json;
using Celeste;
using Microsoft.Xna.Framework;

namespace DeathOracle;

static class RoomCoreCaller
{
    public static object PrepareHeader(Level level, string directory)
    {
        string path = Path.Combine(directory, "presentation-stripped-room.json");
        byte[] bytes = File.ReadAllBytes(path);
        if (Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() != "33cd5d93e1262aec2748cb02ffe1354b1bf46e992de2d49d6c60f4fb3b8fc076")
            throw new InvalidDataException("Declared room input identity changed");
        using var input = JsonDocument.Parse(bytes);
        var room = new LevelData(RoomCoreRoomInput.ReadElement(input.RootElement));
        if (room.Name != "1" || room.LoadSeed != 49 || room.Entities.Count != 6 || room.Triggers.Count != 0)
            throw new InvalidDataException("Declared mechanical room profile changed");
        RoomCoreAreaInput.Configure();
        var area = AreaData.Areas[1];
        var key = new AreaKey(1);
        var map = (MapData)RuntimeHelpers.GetUninitializedObject(typeof(MapData));
        map.Area = key;
        map.Data = area;
        map.ModeData = area.Mode[0];
        map.Levels = new List<LevelData> { room };
        map.Filler = new List<Rectangle>();
        map.Strawberries = room.Entities.Where(entity => entity.Name == "strawberry").ToList();
        map.Goldenberries = room.Entities.Where(entity => entity.Name == "goldenBerry").ToList();
        map.BackgroundColor = Color.Black;
        map.Bounds = room.Bounds;
        map.DetectedStrawberries = room.Strawberries;
        area.Mode[0].MapData = map;
        SaveData.Instance = new SaveData();
        for (int id = 0; id < AreaData.Areas.Count; id++) SaveData.Instance.Areas.Add(new AreaStats(id));
        level.Session = new Session(key, oldStats: SaveData.Instance.Areas[1]);
        level.Background = new BackdropRenderer();
        level.Foreground = new BackdropRenderer();
        level.Displacement = new DisplacementRenderer();
        level.FormationBackdrop = new FormationBackdrop();
        return new { profile = "single-room-header-not-complete-world-caller", room.Name, room.LoadSeed,
            mapConstructorExecuted = false, originalLevelLoaderExecuted = false, remainingWorldCallerIncomplete = true };
    }
}
