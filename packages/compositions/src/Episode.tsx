import { AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Character } from "./components/Character";
import { CalloutPop, Confetti, PropPop } from "./components/Pops";
import { Bubbles, Depth, LayerImg, Lyrics, Petals, Sky, Swimmers } from "./components/Scene";
import { beatInfo, cameraAt, charAt } from "./timeline";
import type { Episode as EpisodeData } from "./types";

export const Episode: React.FC<{ episode: EpisodeData }> = ({ episode: ep }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const cam = cameraAt(ep.camera, t);
  const beat = beatInfo(ep.beats, t);
  // Mouth openness interpolated between track samples → smooth at any render fps.
  const mi = t * (ep.mouthFps ?? 30);
  const m0 = ep.mouth[Math.min(Math.floor(mi), ep.mouth.length - 1)] ?? 0;
  const m1 = ep.mouth[Math.min(Math.floor(mi) + 1, ep.mouth.length - 1)] ?? m0;
  const mouthState = m0 + (m1 - m0) * (mi - Math.floor(mi));

  // Scenes: pick the active scene; during a transition also draw the incoming one, masked.
  const scenes = ep.scenes?.length ? ep.scenes : [{ start: 0, layers: ep.layers }];
  const sceneAt = (time: number) => scenes.reduce((cur, sc) => (sc.start <= time ? sc : cur), scenes[0]);
  const tr = (ep.transitions ?? []).find((x) => t >= x.t - x.dur / 2 && t < x.t + x.dur / 2);
  const outgoing = tr ? sceneAt(tr.t - 0.001) : sceneAt(t);
  const incoming = tr ? sceneAt(tr.t + 0.001) : null;
  const trP = tr ? (t - (tr.t - tr.dur / 2)) / tr.dur : 0;
  const mask = (): React.CSSProperties =>
    !tr
      ? {}
      : tr.type === "iris"
        ? { clipPath: `circle(${Math.pow(trP, 1.6) * 120}% at 50% 55%)` }
        : { transform: `translateX(${(1 - trP * trP * (3 - 2 * trP)) * 100}%)` };
  const layersOf = (sc: { layers: typeof ep.layers }, near: boolean) => sc.layers.filter((l) => (near ? l.depth >= 1 : l.depth < 1));
  const drawLayers = (list: typeof ep.layers, key: string) =>
    list.map((l, i) => (
      <Depth key={`${key}${i}`} depth={l.depth} cam={cam}>
        <LayerImg layer={l} t={t} />
      </Depth>
    ));

  // Draw back-to-front: smaller (farther) characters first, then by lift (flying ones on top).
  const chars = Object.entries(ep.tracks)
    .map(([id, keys]) => ({ id, state: charAt(keys, t, beat.index), prev: charAt(keys, t - 1 / fps, beat.index) }))
    .filter((c): c is { id: string; state: NonNullable<ReturnType<typeof charAt>>; prev: ReturnType<typeof charAt> } => c.state !== null)
    .sort((a, b) => a.state.scale - b.state.scale || a.state.lift - b.state.lift);

  return (
    <AbsoluteFill style={{ overflow: "hidden", background: ep.sky.bottom }}>
      <Audio src={staticFile(ep.audio)} />
      <Depth depth={0.15} cam={cam}>
        <Sky sky={ep.sky} t={t} />
      </Depth>
      {drawLayers(layersOf(outgoing, false), "far")}
      {incoming && (
        <AbsoluteFill style={mask()}>
          <Depth depth={0.15} cam={cam}>
            <Sky sky={ep.sky} t={t} />
          </Depth>
          {drawLayers(layersOf(incoming, false), "farIn")}
        </AbsoluteFill>
      )}
      {ep.swimmers && (
        <Depth depth={0.8} cam={cam}>
          <Swimmers list={ep.swimmers} t={t} />
        </Depth>
      )}
      {ep.sky.kind === "underwater" && (
        <Depth depth={0.9} cam={cam}>
          <Bubbles t={t} />
        </Depth>
      )}
      <Depth depth={1} cam={cam}>
        {ep.props.map((p, i) => (
          <PropPop key={`p${i}`} prop={p} frame={frame} fps={fps} t={t} />
        ))}
        {chars.map(({ id, state, prev }, ci) => (
          <Character
            key={id}
            def={ep.characters[id]}
            state={state}
            groundY={ep.groundY}
            frame={frame}
            t={t}
            beatSince={beat.since}
            singing={ep.singing.some((s) => t >= s.start && t <= s.end && s.who.includes(id))}
            mouthState={mouthState}
            beatIndex={beat.index}
            liftVel={prev ? (state.lift - prev.lift) * fps : 0}
            seed={ci + 1}
          />
        ))}
        {ep.callouts.map((c, i) => (
          <CalloutPop key={`c${i}`} c={c} frame={frame} fps={fps} t={t} />
        ))}
      </Depth>
      {drawLayers(layersOf(outgoing, true), "near")}
      {incoming && <AbsoluteFill style={mask()}>{drawLayers(layersOf(incoming, true), "nearIn")}</AbsoluteFill>}
      {ep.petals && <Petals src={ep.petals.src} count={ep.petals.count} t={t} />}
      {ep.effects.map((e, i) => (e.type === "confetti" ? <Confetti key={`e${i}`} e={e} t={t} /> : null))}
      <Lyrics segments={ep.segments} t={t} lang={ep.lang} />
    </AbsoluteFill>
  );
};
