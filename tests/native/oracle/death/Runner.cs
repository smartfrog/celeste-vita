using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using System.Xml;
using Microsoft.Xna.Framework;
using Monocle;
using Celeste;
using DeathOracle;

static class Runner
{
    static void Main(string[] args)
    {
        GFX.Game = new Atlas();
        using var atlas = JsonDocument.Parse(File.ReadAllText(args[0]));
        foreach (var entry in atlas.RootElement.EnumerateObject())
        {
            var values = entry.Value.EnumerateArray().ToArray();
            GFX.Game.AddMetadata(entry.Name, values[0].GetString(), values.Skip(1).Select(value => value.GetInt32()).ToArray());
        }
        var xml = new XmlDocument(); xml.Load(args[1]);
        GFX.SpriteBank = new SpriteBank(GFX.Game, xml);
        PlayerSprite.CreateFramesMetadata("player");
        Tracker.Initialize();
        using var fixture = JsonDocument.Parse(File.ReadAllText(args[3]));
        if (fixture.RootElement.GetProperty("diagnosticSeed").GetInt32() != 0) throw new Exception("Only diagnostic seed 0 is declared");
        var summaries = new List<object>();
        foreach (var input in fixture.RootElement.GetProperty("cases").EnumerateArray())
            summaries.Add(Run(input, args[2]));
        File.WriteAllText(Path.Combine(args[2], "checkpoint-result.json"), JsonSerializer.Serialize(new {
            status = "blocked-not-source-closed", cases = summaries,
            sourceExecuted = new[] { "Player.Die", "Player.Drop", "PlayerDeadBody", "DeathEffect", "Coroutine", "Tween", "ComponentList", "EntityList", "RendererList", "ScreenWipe", "AngledWipe", "Level.Reload", "Level.UnloadLevel", "Celeste.Freeze", "Engine freeze source block" },
            unsupported = new[] { "Level.Shake RNG/camera effects", "Level.LoadLevel and Player reconstruction", "live physics/input closure", "FNA Vector3/Matrix GPU boundary" },
            diagnosticSeed = 0, originalStartupRngParity = false, coherentLifecycleClosure = false
        }));
        Console.WriteLine("BLOCKED: six dependency diagnostics, zero complete lifecycle gate traces");
    }

    static object Run(JsonElement input, string output)
    {
        Records.Events.Clear(); Draw.SpriteBatch.Calls.Clear(); GFX.WipeVertices.Clear();
        Engine.FreezeTimer = 0;
        Calc.Random = new PresentationOracle.TracedRandom(0);
        var level = new Level();
        level.Session.Time = 1234567; level.Session.Deaths = 7; level.Session.DeathsInCurrentLevel = 3;
        level.Session.FirstLevel = input.GetProperty("firstLevel").GetBoolean();
        level.Session.HitCheckpoint = input.GetProperty("checkpoint").GetBoolean();
        Engine.Scene = level;
        var driver = new FrameDriver { scene = level };
        var position = input.GetProperty("position");
        var direction = input.GetProperty("direction");
        var player = new Player(new Vector2(position[0].GetSingle(), position[1].GetSingle()), level);
        level.Add(player); level.Entities.UpdateLists();
        var body = player.Die(new Vector2(direction[0].GetSingle(), direction[1].GetSingle()));
        body.ActionDelay = input.GetProperty("actionDelay").GetSingle();
        if (!player.Dead || player.Collidable || !player.StateMachine.Locked || body == null)
            throw new Exception("Original Die guards did not execute");
        if (player.Die(new Vector2(-1, 0)) != null) throw new Exception("Duplicate death accepted");
        var rows = new List<object>();
        string blocker = null;
        for (int tick = 0; tick < 180; tick++)
        {
            Input.MenuConfirm.Pressed = tick == input.GetProperty("menuTick").GetInt32();
            Engine.RawDeltaTime = Engine.DeltaTime = 1f / 60f;
            Engine.FrameCounter++;
            bool frozen = Engine.FreezeTimer > 0;
            try
            {
                driver.Tick();
                if (tick == 0 && player.Sprite.CurrentAnimationID != input.GetProperty("animation").GetString()) throw new Exception("Source Awake direction branch mismatch");
                if (!frozen) foreach (PlayerHair hair in level.Tracker.GetComponents<PlayerHair>()) hair.AfterUpdate();
                level.Entities.Render(); level.RendererList.Render();
            }
            catch (UnsupportedClosure error) { blocker = error.Message; }
            var effect = body.Get<DeathEffect>();
            var tween = body.Get<Tween>();
            rows.Add(new { tick, frozen, freeze = Engine.FreezeTimer, level.TimeActive,
                entities = level.Entities.Select(entity => entity.GetType().Name).ToArray(),
                position = new[] { body.Position.X, body.Position.Y }, animation = player.Sprite.CurrentAnimationID,
                frame = player.Sprite.CurrentAnimationFrame, rotation = player.Sprite.Rotation,
                scale = new[] { player.Sprite.Scale.X, player.Sprite.Scale.Y },
                hairOwner = player.Hair.Entity.GetType().Name,
                nodes = player.Hair.Nodes.Select(node => new[] { node.X, node.Y }).ToArray(),
                tween = tween == null ? null : new { tween.Active, tween.Percent, tween.Eased, tween.TimeLeft },
                effect = effect == null ? null : new { effect.Percent, effect.Duration },
                wipe = level.Wipe == null ? null : new { level.Wipe.Percent, level.Wipe.Completed },
                draws = Draw.SpriteBatch.Calls.Count, rng = Calc.Random.Calls,
                events = Records.Events.ToArray(), blocker });
            if (blocker != null) break;
        }
        File.WriteAllText(Path.Combine(output, input.GetProperty("id").GetString() + ".json"), JsonSerializer.Serialize(rows));
        if (blocker == null || !blocker.StartsWith("Celeste.Level.LoadLevel:")) throw new Exception("Mandatory reload dependency was not reached");
        bool resetSession = level.Session.FirstLevel && !level.Session.HitCheckpoint;
        if (level.Session.Deaths != (resetSession ? 0 : 8) || level.Session.DeathsInCurrentLevel != 4 ||
            level.Session.Time != (resetSession ? 0 : 1234567)) throw new Exception("Original Reload counter branch mismatch");
        if (Draw.SpriteBatch.Calls.Count == 0 || GFX.WipeVertices.Count == 0) throw new Exception("Missing original draw execution");
        return new { id = input.GetProperty("id").GetString(), ticks = rows.Count, blocker,
            events = Records.Events.ToArray(), draws = Draw.SpriteBatch.Calls.Count, wipeDraws = GFX.WipeVertices.Count,
            session = new { level.Session.Deaths, level.Session.DeathsInCurrentLevel, level.Session.Time } };
    }
}
