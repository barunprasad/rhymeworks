// episode.json contract consumed by the renderer. Times are seconds; positions are stage pixels
// on a 1920×1080 stage before camera transform. Image anchors are fractions of the (cut) image.

export type Word = { w: string; start: number; end: number };
export type Segment = { text: string; start: number; end: number; words: Word[] };

export type Pose = {
  src: string;
  w: number;
  h: number;
  mouth?: { x: number; y: number; width: number };
};

export type RigPart = { name: string; src: string; x: number; y: number; w: number; h: number; z: number };
export type RigEye = { src: string; x: number; y: number; w: number; h: number; cx: number; cy: number; r: number };

/** Auto-rig from lookdev/rig.py; coordinates are rig-image pixels. `base` prefixes part srcs. */
export type RigDef = {
  kind?: "octo"; // head + tentacle skirt (no limbs)
  base: string;
  size: [number, number];
  skin: string;
  parts: RigPart[];
  pivots: Record<string, { x: number; y: number }>;
  rest?: Record<string, number>; // drawn arm angle vs hanging down (deg)
  eyes: RigEye[];
  mouth: { x: number; y: number; width: number } | null;
};

export type CharacterDef = {
  rig?: RigDef; // when present, track `pose` values are rig action names
  poses: Record<string, Pose>;
  height: number; // on-stage height in px at scale 1
  mouthMode: "svg" | "beak" | "none";
  beak?: { half: string; open: string };
  fly?: { up: string; down: string };
};

export type Move = "hop" | "walk" | "fly" | "jump" | "slide";

export type Keyframe = {
  t: number;
  x: number;
  y?: number; // height above ground in px (positive = up)
  pose: string;
  move?: Move; // how to travel from the previous keyframe to this one
  facing?: 1 | -1;
  beatPoses?: string[]; // cycle through these on each beat while holding
  scale?: number;
  look?: { x: number; y: number }; // pupil direction for rigged characters, −1..1
};

export type CameraKey = { t: number; cx: number; cy: number; zoom: number; cut?: boolean };

export type Layer = {
  src: string;
  depth: number; // 0 = infinitely far, 1 = character plane, >1 = foreground
  x: number;
  y: number;
  w: number;
  h: number;
  sway?: number; // degrees of skew sway (plants)
  glow?: string; // pulsing halo colour (e.g. a deity image)
  breathe?: number; // gentle scale pulse amplitude (e.g. 0.015)
};

export type Prop = {
  src: string;
  t: number;
  until?: number;
  x: number;
  y: number;
  h: number;
  label?: string;
  labelColor?: string;
};

export type Callout = { t: number; text: string; x: number; y: number; color?: string; dur?: number };

export type Effect = { type: "confetti"; t: number; dur?: number };

export type Swimmer = { src: string; y: number; size: number; speed: number; dir: 1 | -1; start: number; bob?: number };

export type SceneDef = { start: number; layers: Layer[] };
export type Transition = { t: number; type: "iris" | "slide"; dur: number };

export type Sing = { start: number; end: number; who: string[] };

export type Episode = {
  fps: number;
  durationSec: number;
  audio: string;
  lang: "en" | "hi";
  groundY: number;
  beats: number[];
  mouth: number[]; // mouth openness 0..3 sampled at mouthFps from the vocal envelope
  mouthFps?: number; // defaults to 30 (independent of render fps)
  segments: Segment[];
  sky: { top: string; bottom: string; clouds: string; sun: string; kind?: "day" | "underwater" };
  swimmers?: Swimmer[];
  petals?: { src: string; count: number }; // falling flower petals across the frame
  layers: Layer[];
  scenes?: SceneDef[]; // when set, overrides `layers` per time range
  transitions?: Transition[];
  characters: Record<string, CharacterDef>;
  tracks: Record<string, Keyframe[]>;
  singing: Sing[];
  camera: CameraKey[];
  props: Prop[];
  callouts: Callout[];
  effects: Effect[];
};
