import { Composition } from "remotion";
import { Episode } from "./Episode";
import type { Episode as EpisodeData } from "./types";

const empty: EpisodeData = {
  fps: 30,
  durationSec: 5,
  audio: "",
  lang: "en",
  groundY: 900,
  beats: [],
  mouth: [],
  segments: [],
  sky: { top: "#9fdcff", bottom: "#e9f8ff", clouds: "", sun: "" },
  layers: [],
  characters: {},
  tracks: {},
  singing: [],
  camera: [],
  props: [],
  callouts: [],
  effects: [],
};

// Real data arrives via --props='{"episode": ...}' (or --props=path/to/props.json).
export const Root: React.FC = () => (
  <Composition
    id="Episode"
    component={Episode}
    width={1920}
    height={1080}
    fps={30}
    durationInFrames={150}
    defaultProps={{ episode: empty }}
    calculateMetadata={({ props }) => ({
      fps: props.episode.fps,
      durationInFrames: Math.max(1, Math.round(props.episode.durationSec * props.episode.fps)),
    })}
  />
);
