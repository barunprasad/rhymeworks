import { Img, staticFile } from "remotion";
import type { CharacterDef } from "../types";
import type { CharState } from "../timeline";
import { Mouth } from "./Mouth";
import { actionJoints, beatEnvelope, blendJoints, octoJoints, RigBody } from "./Rig";

type Props = {
  def: CharacterDef;
  state: CharState;
  groundY: number;
  frame: number;
  t: number;
  beatSince: number;
  singing: boolean;
  mouthState: number;
  beatIndex: number;
  liftVel: number; // px/s, for secondary motion
  seed: number;
};

export const Character: React.FC<Props> = ({ def, state, groundY, frame, t, beatSince, singing, mouthState, beatIndex, liftVel, seed }) => {
  let poseName = state.pose;
  if (state.move === "fly" && def.fly) poseName = Math.floor(t * 7.5) % 2 ? def.fly.up : def.fly.down; // time-based: same flap rate at any fps
  if (def.mouthMode === "beak" && def.beak && singing && poseName === "base") {
    poseName = mouthState >= 1.6 ? def.beak.open : mouthState >= 0.6 ? def.beak.half : "base";
  }
  const pose = def.poses[poseName] ?? def.poses.base;
  const rig = def.rig;

  const H = def.height * state.scale;
  const W = rig ? (H * rig.size[0]) / rig.size[1] : (H * pose.w) / pose.h;

  let rigJoints = null;
  if (rig) {
    const beatPhase = Math.min(beatSince, 1);
    const walkPhase = state.since * Math.PI * 2 * 2.2;
    const octo = rig.kind === "octo";
    const cur = octo ? octoJoints(state.pose, t, beatPhase, beatIndex, state.since) : actionJoints(state.pose, t, beatPhase, beatIndex, state.moving, walkPhase);
    const prev = octo ? octoJoints(state.prevPose, t, beatPhase, beatIndex, 99) : actionJoints(state.prevPose, t, beatPhase, beatIndex, false, walkPhase);
    const p = Math.min(1, state.since / 0.18);
    rigJoints = blendJoints(prev, cur, p * p * (3 - 2 * p));
    if (octo) rigJoints.spin = cur.spin; // spins must not blend from 0 (would look like a half turn)
    // Antenna lags vertical motion (springy) and wobbles a little.
    rigJoints.antenna = Math.sin(t * 4.5 + seed) * 4 + Math.max(-25, Math.min(25, liftVel * 0.03));
  }
  const look = state.look ?? { x: Math.sin(t * 0.6 + seed) * 0.35, y: Math.sin(t * 0.43 + seed * 2) * 0.2 };

  // Squash & stretch on the beat while grounded; idle breathing + sway always.
  const grounded = state.lift < 4 && !state.moving;
  // Eased beat accent: 60 ms ramp-in, 250 ms ease-out (no single-frame jumps).
  const pulse = grounded ? beatEnvelope(beatSince) : 0;
  const breathe = Math.sin(t * 3.1) * 0.012;
  const sy = 1 - 0.07 * pulse + breathe;
  const sx = 1 + 0.05 * pulse - breathe * 0.6;
  // Stretch while airborne (jumps/hops), lean into travel direction.
  const air = Math.min(1, state.lift / 120);
  const stretchY = 1 + air * 0.08;
  const stretchX = 1 - air * 0.05;
  const sway = Math.sin(t * 2.2 + state.x * 0.01) * (state.moving ? 4 : 1.8);
  const flyBob = state.move === "fly" ? Math.sin(t * 9) * 10 : 0;

  const left = state.x - W / 2;
  const top = groundY - H - state.lift - flyBob;

  const shadowW = W * 0.62 * (1 - Math.min(0.6, state.lift / 400));
  const shadowOpacity = 0.22 * (1 - Math.min(0.85, state.lift / 300));

  return (
    <>
      <div
        style={{
          position: "absolute",
          left: state.x - shadowW / 2,
          top: groundY - shadowW * 0.09,
          width: shadowW,
          height: shadowW * 0.18,
          borderRadius: "50%",
          background: `rgba(40, 60, 30, ${shadowOpacity})`,
          filter: "blur(3px)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left,
          top,
          width: W,
          height: H,
          transformOrigin: "50% 100%",
          transform: `scaleX(${state.facing * sx * stretchX}) scaleY(${sy * stretchY}) rotate(${sway * state.facing}deg)`,
        }}
      >
        {rig && rigJoints ? (
          <RigBody rig={rig} W={W} H={H} joints={rigJoints} t={t} blinkSeed={seed} look={look} mouthState={def.mouthMode === "svg" ? (singing ? mouthState : 0) : null} />
        ) : (
          <Img src={staticFile(pose.src)} style={{ width: W, height: H, display: "block" }} />
        )}
        {!rig && def.mouthMode === "svg" && pose.mouth && (
          <div
            style={{
              position: "absolute",
              left: (pose.mouth.x - pose.mouth.width / 2) * W,
              // Anchor y is a fraction of height, width a fraction of width; the mouth path's
              // visual centre sits ~30% down its own box.
              top: pose.mouth.y * H - pose.mouth.width * W * 0.3,
              transform: state.facing < 0 ? "scaleX(-1)" : undefined,
            }}
          >
            <Mouth state={singing ? mouthState : 0} width={pose.mouth.width * W} />
          </div>
        )}
      </div>
    </>
  );
};
