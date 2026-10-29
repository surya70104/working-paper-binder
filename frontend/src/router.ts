// A hash router: four screens, no dependency.
//   #/                          binders
//   #/binders/<id>              one binder: index tree, completeness, countdown
//   #/binders/<id>/assembly     assembly and retention: blockers, manifest, produce, purge
//   #/papers/<id>               one working paper: fields, attachments, versions, sign-off
import { useEffect, useState } from "react";

export type Route =
  | { name: "binders" }
  | { name: "binder"; id: string }
  | { name: "assembly"; id: string }
  | { name: "review-notes"; id: string }
  | { name: "paper"; id: string };

export function parseRoute(hash: string): Route {
  const path = hash.replace(/^#/, "");
  const assembly = /^\/binders\/([^/]+)\/assembly$/.exec(path);
  if (assembly?.[1]) return { name: "assembly", id: assembly[1] };
  const notes = /^\/binders\/([^/]+)\/review-notes$/.exec(path);
  if (notes?.[1]) return { name: "review-notes", id: notes[1] };
  const binder = /^\/binders\/([^/]+)$/.exec(path);
  if (binder?.[1]) return { name: "binder", id: binder[1] };
  const paper = /^\/papers\/([^/]+)$/.exec(path);
  if (paper?.[1]) return { name: "paper", id: paper[1] };
  return { name: "binders" };
}

export function href(route: Route): string {
  switch (route.name) {
    case "binders":
      return "#/";
    case "binder":
      return `#/binders/${route.id}`;
    case "assembly":
      return `#/binders/${route.id}/assembly`;
    case "review-notes":
      return `#/binders/${route.id}/review-notes`;
    case "paper":
      return `#/papers/${route.id}`;
  }
}

export function navigate(route: Route): void {
  window.location.hash = href(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
