import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ComingSoonPage } from "./pages/ComingSoonPage";
import { DashboardPage } from "./pages/DashboardPage";
import { KeyboardPage } from "./pages/KeyboardPage";
import { MusicFavoritesPage } from "./pages/MusicFavoritesPage";
import { MusicLibraryPage } from "./pages/MusicLibraryPage";
import { MusicPlayerPage } from "./pages/MusicPlayerPage";
import { MusicPlaylistsPage } from "./pages/MusicPlaylistsPage";
import { MusicRecentPage } from "./pages/MusicRecentPage";
import { MusicSourcesPage } from "./pages/MusicSourcesPage";
import { ScoreEditorPage } from "./pages/ScoreEditorPage";
import { ScoresPage } from "./pages/ScoresPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TranscriptionPage } from "./pages/TranscriptionPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />

        <Route path="/music-library" element={<MusicLibraryPage />} />
        <Route path="/music-favorites" element={<MusicFavoritesPage />} />
        <Route path="/music-playlists" element={<MusicPlaylistsPage />} />
        <Route path="/music-recent" element={<MusicRecentPage />} />
        <Route path="/music-sources" element={<MusicSourcesPage />} />
        <Route path="/music-player" element={<MusicPlayerPage />} />

        <Route path="/transcription" element={<TranscriptionPage />} />
        <Route path="/scores" element={<ScoresPage />} />
        <Route path="/scores/:documentId" element={<ScoreEditorPage />} />
        <Route path="/keyboard" element={<KeyboardPage />} />
        <Route path="/settings" element={<SettingsPage />} />

        <Route path="*" element={<ComingSoonPage stage="V1.0-A" title="页面不存在" />} />
      </Route>
    </Routes>
  );
}
