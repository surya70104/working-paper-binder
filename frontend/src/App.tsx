import { AssemblyPage } from "./pages/AssemblyPage";
import { BinderPage } from "./pages/BinderPage";
import { BindersPage } from "./pages/BindersPage";
import { PaperPage } from "./pages/PaperPage";
import { ReviewNotesPage } from "./pages/ReviewNotesPage";
import { XrefMapPage } from "./pages/XrefMapPage";
import { useRoute } from "./router";

export function App() {
  const route = useRoute();
  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-baseline gap-3 px-6 py-3">
          <a href="#/" className="text-lg font-semibold hover:underline">
            Working Paper Binder
          </a>
          <span className="text-sm text-slate-500">SA 230 · OAK Audit</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-6">
        {route.name === "binders" && <BindersPage />}
        {route.name === "binder" && <BinderPage id={route.id} />}
        {route.name === "assembly" && <AssemblyPage id={route.id} />}
        {route.name === "review-notes" && <ReviewNotesPage id={route.id} />}
        {route.name === "xref-map" && <XrefMapPage id={route.id} />}
        {route.name === "paper" && <PaperPage id={route.id} />}
      </main>
    </div>
  );
}
