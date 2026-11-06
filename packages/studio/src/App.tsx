import { useEffect, useMemo } from "react";
import { EventHub, HubContext } from "./api";
import { href, useRoute } from "./router";
import { Sidebar } from "./components/Sidebar";
import { ProjectProvider } from "./components/Project";
import { TabBar, TopBar } from "./components/MobileBars";
import { EpisodesPage, Home } from "./pages/Home";
import { LibraryPage } from "./pages/Library";
import { EpisodePage } from "./pages/Episode";
import { ReviewPage } from "./pages/Review";
import { QueuePage } from "./pages/Queue";
import { ShotListPage } from "./pages/ShotList";
import { NewEpisodePage } from "./pages/NewEpisode";
import { UploadPage } from "./pages/Upload";
import { DraftPage, KIND_WORD, NewAssetPage } from "./pages/NewAsset";
import { SongPage } from "./pages/Song";
import { VoicesPage } from "./pages/Voices";
import { AnimaticPage } from "./pages/Animatic";
import { OptionsPage } from "./pages/Options";
import { DirectorPage } from "./pages/Director";

// Mobile first: phones get a top bar + bottom tabs; from 900 px the sidebar takes over (see styles.css).
export function App() {
  const hub = useMemo(() => new EventHub(), []);
  useEffect(() => hub.start(), [hub]);
  const route = useRoute();
  const [section, slug, sub, stage] = route;
  const reviewing = section === "episodes" && !!slug && sub === "review" && (stage === "keys" || stage === "clips");

  let page, back;
  let focus = reviewing;   // focused tasks bring their own bottom action bar instead of the tabs
  if (section === "library" && slug === "new" && (sub === "cast" || sub === "props" || sub === "scenes")) {
    page = <NewAssetPage kind={sub} />;
    back = { to: href("library", sub), label: "Back to library", title: `New ${KIND_WORD[sub]}` };
  } else if (section === "library" && slug === "draft" && sub) {
    page = <DraftPage id={sub} />;
    back = { to: href("library", "cast"), label: "Back to library", title: "New in the library" };
    focus = true;
  } else if (section === "library" && slug === "voices") page = <VoicesPage />;
  else if (section === "library") page = <LibraryPage tab={slug ?? "all"} />;
  else if (section === "queue") page = <QueuePage />;
  else if (reviewing) {
    page = <ReviewPage slug={slug} stage={stage as "keys" | "clips"} />;
    back = { to: href("episodes", slug), label: "Back to episode", title: `Review ${stage === "keys" ? "keyframes" : "clips"}` };
  } else if (section === "episodes" && slug === "new") {
    page = <NewEpisodePage from={sub} />;
    back = { to: href("episodes"), label: "Back to episodes", title: "New episode" };
  } else if (section === "episodes" && slug && sub === "shots") {
    page = <ShotListPage slug={slug} />;
    back = { to: href("episodes", slug), label: "Back to episode", title: "Shot list" };
    focus = true;
  } else if (section === "episodes" && slug && sub === "song") {
    page = <SongPage slug={slug} />;
    back = { to: href("episodes", slug), label: "Back to episode", title: "Song" };
    focus = true;
  } else if (section === "episodes" && slug && sub === "watch") {
    page = <AnimaticPage slug={slug} start={stage} />;
    back = { to: href("episodes", slug), label: "Back to episode", title: "Animatic", sub: "Keyframes on the song" };
    focus = true;
  } else if (section === "episodes" && slug && sub === "options" && stage) {
    page = <OptionsPage slug={slug} sid={stage} />;
    back = { to: href("episodes", slug, "watch", stage), label: "Back to the animatic", title: "Pick the keyframe", sub: stage };
    focus = true;
  } else if (section === "episodes" && slug && sub === "director") {
    page = <DirectorPage slug={slug} shot={stage} />;
    back = { to: href("episodes", slug), label: "Back to episode", title: "Director", sub: "Changes the shot list for you" };
  } else if (section === "episodes" && slug && sub === "upload") {
    page = <UploadPage slug={slug} />;
    back = { to: href("episodes", slug), label: "Back to episode", title: "Upload pack" };
    focus = true;
  } else if (section === "episodes" && slug) {
    page = <EpisodePage slug={slug} />;
    back = { to: href("episodes"), label: "Back to episodes", title: "Episode" };
  } else if (section === "episodes") page = <EpisodesPage />;
  else page = <Home />;

  return (
    <HubContext.Provider value={hub}>
      <ProjectProvider>
      {/* review is a focused task on phones: no tab bar, its own Approve / Redo bar instead */}
      <div className={`app ${focus ? "focus" : ""}`}>
        <TopBar back={back} />
        <Sidebar route={route} />
        <main className="main">{page}</main>
        {!focus && <TabBar section={section ?? ""} />}
      </div>
      </ProjectProvider>
    </HubContext.Provider>
  );
}
