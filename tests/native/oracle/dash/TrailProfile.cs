using System;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using Celeste;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Microsoft.Xna.Framework.Input;
using Monocle;

namespace DeathOracle {
public static class TrailRecording {
    public static Action<object> Observe;
    static BlendState blend;
    public static void Begin(object[] arguments) {
        blend=arguments.OfType<BlendState>().SingleOrDefault();
        Observe?.Invoke(new { operation="begin", source=blend?.ColorSourceBlend.ToString(),destination=blend?.ColorDestinationBlend.ToString(),
            alphaSource=blend?.AlphaSourceBlend.ToString(),alphaDestination=blend?.AlphaDestinationBlend.ToString(),function=blend?.ColorBlendFunction.ToString() });
    }
    public static void Rect(float x,float y,float width,float height,Color color) =>
        Observe?.Invoke(new { operation="rect",x,y,width,height,color=new[]{(int)color.R,color.G,color.B,color.A} });
    public static void Draw(Texture2D texture,Vector2 position,Rectangle clip,Color color,float rotation,Vector2 origin,Vector2 scale,SpriteEffects effects) {
        var g=LifecycleRecording.Batch.Geometry.Calls.Last();
        Observe?.Invoke(new { operation="draw",target=texture is RenderTarget2D,texture=texture.Name,
            position=new[]{position.X,position.Y},clip=new[]{clip.X,clip.Y,clip.Width,clip.Height},
            color=new[]{(int)color.R,color.G,color.B,color.A},rotation,origin=new[]{origin.X,origin.Y},scale=new[]{scale.X,scale.Y},
            vertices=new[]{new[]{g.Position0.X,g.Position0.Y},new[]{g.Position1.X,g.Position1.Y},new[]{g.Position3.X,g.Position3.Y},new[]{g.Position2.X,g.Position2.Y}} });
    }
}
static partial class RoomCoreExecution {
    static void Main(string[] args) {
        if(args.Length>0 && args[0]=="native-abi-metadata-audit") { NativeAbiMetadataAudit.Run(args);return; }
        if(args.Length>0 && args[0].StartsWith("native-abi-",StringComparison.Ordinal)) { NativeImportGuardProbe.Run(args);return; }
        if(args.Length!=3) throw new ArgumentException("Expected trace, tile-content and input-only scenario");
        using var probe=new Probe(args,0);
        try {
            PrepareGroundedRoom(probe,args[1]);
            Settings.Instance.Rumble=RumbleAmount.Off;
            Settings.Instance.Right.Add(Keys.Right);Settings.Instance.Left.Add(Keys.Left);
            Settings.Instance.Up.Add(Keys.Up);Settings.Instance.Down.Add(Keys.Down);
            Settings.Instance.Jump.Add(Keys.C);Settings.Instance.Dash.Add(Keys.X);
            Input.Initialize();
            Input.Jump.Binding.Controller.Clear();Input.Dash.Binding.Controller.Clear();Input.CrouchDash.Binding.Controller.Clear();
            RoomCoreParticleInput.Configure();
            probe.Level.LoadLevel(Player.IntroTypes.Respawn);
            var graphics=(GraphicsDeviceManager)RuntimeHelpers.GetUninitializedObject(typeof(GraphicsDeviceManager));
            typeof(GraphicsDeviceManager).GetField("graphicsDevice",BindingFlags.Instance|BindingFlags.NonPublic).SetValue(graphics,new GraphicsDevice());
            typeof(Engine).GetProperty("Graphics").GetSetMethod(true).Invoke(null,new object[]{graphics});
            var driver=new FrameDriver{scene=probe.Level};
            KeyboardState previous=default;
            if(!new[]{"first","repeat","cancel","reload","capacity","fractional"}.Contains(args[2])) throw new ArgumentException("Unknown input-only scenario");
            for(int tick=0;tick<360;++tick) {
                var keysList=new System.Collections.Generic.List<Keys>();
                bool api=args[2] is "capacity" or "fractional";
                if(!api) {
                    if(tick>=40 && tick<60) keysList.Add(args[2] is "cancel" or "reload" ? Keys.Right : Keys.Up);
                    if(tick==40 || (args[2]=="repeat" && tick==130)) keysList.Add(Keys.X);
                    if(args[2]=="repeat" && tick>=130 && tick<150) keysList.Add(Keys.Up);
                    if(args[2]=="cancel" && tick==46) keysList.Add(Keys.C);
                }
                Keys[] keys=keysList.ToArray();
                SetEngineTick(1f/60f);
                MInput.Keyboard.PreviousState=previous;MInput.Keyboard.CurrentState=new KeyboardState(keys);
                Input.MoveX.Update();Input.MoveY.Update();Input.Aim.Update();Input.Jump.Update();Input.Dash.Update();Input.CrouchDash.Update();
                bool frozen=Engine.FreezeTimer>0;
                driver.Tick();
                if(tick==39 && args[2]=="capacity") {
                    var prime=probe.Level.Tracker.GetEntity<Player>();
                    TrailManager.Add(prime.Position,prime.Sprite,prime.Hair,prime.Sprite.Scale,new Color(68,183,255),1);
                }
                if(tick==40 && api) {
                    var live=probe.Level.Tracker.GetEntity<Player>();
                    var anchor=args[2]=="fractional" ? new Vector2(19.25f,144.75f) : live.Position;
                    for(int i=0;i<(args[2]=="capacity" ? 65 : 1);++i) {
                        var added=TrailManager.Add(anchor,live.Sprite,live.Hair,live.Sprite.Scale,new Color(68,183,255),1);
                        probe.Write(new{@event="pool-api-fixture",tick,ordinal=i,slot=added?.Index,anchor=new[]{anchor.X,anchor.Y}});
                    }
                }
                var manager=probe.Level.Tracker.GetEntity<TrailManager>();
                var pending=PendingEntities(probe.Level).OfType<TrailManager.Snapshot>().ToArray();
                var snapshots=probe.Level.Entities.OfType<TrailManager.Snapshot>().ToArray();
                var player=probe.Level.Tracker.GetEntity<Player>();
                probe.Write(new { @event="trails",tick,frozen,committed=snapshots.Select(s=>new{s.Index,s.Percent,s.Drawn,position=new[]{s.Position.X,s.Position.Y},scale=new[]{s.SpriteScale.X,s.SpriteScale.Y},s.Depth}).ToArray(),
                    pending=pending.Select(s=>new{s.Index,s.Percent,s.Drawn,position=new[]{s.Position.X,s.Position.Y},scale=new[]{s.SpriteScale.X,s.SpriteScale.Y}}).ToArray(),state=player?.StateMachine.State,dashes=player?.Dashes,
                    dash=Input.Dash.Pressed,keys=keys.Select(k=>k.ToString()).ToArray(),position=player==null ? null : new[]{player.Position.X,player.Position.Y} });
                LifecycleRecording.Begin();
                int gpuStart=GpuRecords.Commands.Count;
                TrailRecording.Observe=row=>probe.Write(new{@event="recording",tick,row});
                try {
                    foreach(BeforeRenderHook hook in probe.Level.Tracker.GetComponents<BeforeRenderHook>()) hook.Callback();
                    foreach(var snapshot in snapshots) snapshot.Render();
                    var owner=probe.Level.Entities.FirstOrDefault(entity=>entity is Player || entity is PlayerDeadBody);
                    owner?.Render();
                    foreach(var command in GpuRecords.Commands.Skip(gpuStart)) probe.Write(new{@event="gpu",tick,command.Operation,
                        arguments=command.Arguments.Select(value=>value is RenderTarget2D target ? (object)new{type="RenderTarget2D",target.Width,target.Height} : value?.ToString()).ToArray()});
                } finally {TrailRecording.Observe=null;LifecycleRecording.End();}
                previous=MInput.Keyboard.CurrentState;
            }
            probe.Write(new{@event="completed",nativeAttempts=NativeImportGuard.Attempts.Length,backend="recording-only-no-GPU-pixels"});
        } catch(Exception error) { probe.Write(new{@event="boundary",error=error.ToString(),nativeAttempts=NativeImportGuard.Attempts});throw; }
    }
}
}
namespace Celeste {
public static class SlashFx { public static void Burst(Vector2 position,float direction) => DeathOracle.GpuRecords.Add("excluded-slash",position,direction); }
public sealed class PlayerDashAssist : Entity {
    public float Direction,Scale;public Vector2 Offset;
    public PlayerDashAssist() => throw new DeathOracle.UnsupportedClosure("Dash Assist excluded from the default-inventory trail profile");
}
}
