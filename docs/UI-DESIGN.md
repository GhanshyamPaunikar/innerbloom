# Reflect: warm sculptural glass

Implemented from the selected second mockup: cream architectural surroundings, frosted navigation, near-opaque ivory reading surfaces, thin geometric lettering, charcoal capsule controls, and one orange disc behind a frosted strip. The visual should feel like a personal room, with writing and evidence taking priority.

## Feature coverage

- Writing: title, body, local draft recovery, optional personal intensity rating, save with local model analysis, focus mode, daily prompts, recent entries, on-device dictation when supported.
- Archive: text and emotion filters, newest/oldest sorting, month calendar, day filtering, entry view/edit/delete, reflection questions and related entries.
- Conversations: journal/general modes, three personas, streaming responses, retrieval steps and source citations.
- Insights: overview chart and stats, 365-day writing habits, weekly/monthly/all-entry reflections, contradictions, triggers, wellbeing and narrative.
- Memory map: theme clusters, drag/pan/zoom, reset, entry details and an accessible alternative entry list.
- Music: existing Spotify setup, connection status, listening history, audio/mood views and listening-pattern analysis.
- Settings: visual preferences, Spotify configuration, Markdown export, conversation clearing and model information. Command palette and crisis support overlay retained.

## Critique and changes during implementation

1. A fully translucent editor made the backdrop compete with the writing. Reading surfaces are now almost opaque; the strongest glass treatment stays in navigation and decorative panels.
2. The first overview consumed too much vertical room on laptops. Reduced chart height, panel padding and navigation spacing at short viewport heights; deeper insight tools now have separate tabs.
3. An intensity curve can imply a wellbeing score. Labels now explicitly say model-estimated intensity; missing days are not joined, and personal ratings appear separately in entry details.
4. Original drafts restored only body text. Title and optional rating now restore too, and pending autosaves cannot bring back a just-saved draft.
5. Original graph forces could fling dense connections offscreen. Forces and velocities are bounded, positions stay inside the graph, and reset/zoom controls are provided.
6. Small-screen testing caught a squeezed menu icon and an overlapping legacy breakpoint. Fixed the icon and aligned navigation breakpoints at 780px. Collapsed navigation is hidden from keyboard and accessibility navigation.
7. Added visible focus, arrow-key insight tabs, modal focus handling, chart descriptions, a graph entry list, reduced motion styles, and quiet-background/opaque-panel preferences.

## Local operation

Run `python run_local.py`, then open `http://127.0.0.1:5000/app`. The process binds to loopback. Only `/assets` is mounted as static content; repository files and the data directory are not exposed by the static server. Existing JSON schemas and backend AI routes remain intact.

No frontend analytics, remote fonts, CDN scripts or remote background images were added. Optional Spotify uses the network. Dictation requires browser support for `processLocally` and an already-installed English language pack; it never silently falls back to cloud speech recognition. Actual voice recognition was not exercised.

Run `python run_local.py --demo --port 8766` for an isolated design preview. The banner identifies fictional data and simulated AI. The fixture writes only to a temporary directory and skips Ollama calls. It is not a substitute for verifying real model quality or Spotify OAuth.

## Assets and code

- `index.html`: view structure and local asset loading.
- `assets/base.css`, `assets/glass.css`: preserved component baseline and new design system.
- `assets/app.js`: preserved application behavior, with fixes described above.
- `assets/workspace.js`: new layout interactions, calendar, preferences and accessibility.
- `assets/fonts/Urbanist-Variable.ttf`: bundled Urbanist variable font; OFL license alongside it. Upstream: https://github.com/google/fonts/tree/main/ofl/urbanist.
- `assets/images/sculptural-room.webp`: generated backdrop, optimized to about 52 KB. Art direction: a warm ivory architectural still life with a large glass sphere, pale stone and soft daylight; open central space for UI, no typography or interface baked into the image. It is a static image; panels and orange disc are native CSS.

## Verification

- Existing backend suite: 69 passing checks, Ollama and Spotify mocked.
- New UI-serving suite: three passing tests for assets, demo identification, and rejection of private/repository static paths.
- JavaScript syntax checks passed; git whitespace check passed.
- Browser: draft title/body/rating survived reload; save and edit persisted to the temporary preview backend. Archive search, day filtering, empty results and sorting worked. All seven insight panels navigated; reflection and conversation responses rendered. Preferences persisted after reload. Command navigation worked. Mobile navigation, chart layout and graph checked at 390px; desktop checked at 1280px and the native browser viewport. No captured browser console errors.
- Live Ollama inference, microphone capture and real Spotify login have not been tested in this session. Those require the local service/browser support or a connected account.

## Second review: user feedback, November 1

The user identified remaining dashboard-like components. These were replaced, rather than simply recolored:

- The jagged canvas intensity curve is now a selectable daily display. Each bar represents an actual daily estimate; absent dates remain empty. The detail row links to that day's entries.
- The annual heatmap is now a month-by-month writing calendar with entry counts and direct day navigation.
- The force graph is replaced by a named-memory explorer. Each source card has a date and title; each branch lists the shared features returned by the graph API. Three connections are shown per page, ranked by weight. Both the original entry and any related entry can be opened. Search and follow actions remain available. This intentionally replaces pan/zoom and the unreadable all-node view.
- Feeling filters are a compact dropdown; emotion metadata is unboxed; topics and supporting evidence use readable rows. Conversation starters are numbered prompts. Header search is one integrated control. Wellbeing measurement details are disclosed on demand beneath plain-language summaries.
- Spotify setup has a record-sleeve composition. The connected screen prioritizes real album art, recent tracks and top tracks, then listening/writing comparisons. The old technical fallback banner and synthetic obscurity score were removed from presentation. Genre estimates remain available in a disclosure. The daily listening ledger uses available observations and describes the limits of the recent-history sample.

Spotify was configured locally from the user-supplied Client ID and exact registered URI, `http://127.0.0.1:5500/index.html`. The server now serves the workspace at that path, and PKCE uses the same origin for callback storage. OAuth state validation was added. After the user expressly approved the Spotify consent screen, the callback completed and actual recent/top tracks and album art loaded. Tokens are in the ignored local Spotify data file; they are not in source. Reference: [Spotify PKCE documentation](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow). Start this configuration with `python run_local.py --port 5500`.

Verification: 69 backend checks and four UI-serving tests pass. Browser checks verified connection pagination, following and opening a dated memory, month switching and day filtering, feeling filtering, daily intensity-to-entry navigation, and live Spotify authentication/data loading. At 390px, testing caught and fixed an intrinsic grid-width overflow in the memory list. Browser console checks were clear. The local Ollama service is offline, so live local-model generation remains unverified.

## Spatial-map and chart follow-up

Removed the outlined placeholders for days without entries: these now use a quiet, filled canvas tone, with their dates and accessible descriptions preserved. The local sample seeder can generate a complete 150-day fictional fixture (while preserving user entries and remaining idempotent). Replaced the connection-list layout with a desktop spatial map: selected memory in the centre, four connected cards around it, continuous curved lines, and shared-topic labels within each connected card. Clicking a card recentres the map; separate read controls open the original entries. Additional neighbours are paginated. The memory index is now a horizontal strip above the map.

## Innerbloom rename, People and memory groups

The design was first built on an older copy of the code, then reapplied on top of the later Innerbloom work: the rename, month-ago surfacing, local notifications, the Companion/Observer/Challenger voices, background insight refresh, and the People CRM. Those features keep their behaviour and are restyled to fit:

- People uses the server-side CRM (`/people`): cards per person with dominant emotions, themes and entry dates, and a detail drawer for relationship, birthday, check-in cadence, notes and "I reached out". A person first seen in imported entries keeps their written name when first edited.
- The month-ago pill sits beside the date in the editor and opens the then-and-now comparison.
- Voices are a capsule picker; the active voice uses the charcoal control colour.
- Notifications and the insight refresh badge are unchanged in behaviour.
- Memory map (`assets/memory-map.js`, `assets/memory-map.css`) replaces the force graph. Connections are computed in the browser from shared themes and tags (at least two shared, Jaccard overlap of 0.25 or more). Entries are grouped by weighted label propagation and each group is named from its two most common terms. Groups with fewer than three entries count as individual memories. The map can be limited to all time, the last two years or the last three months. Selecting a dot shows the entry and its connected memories in a side panel.
- The Music page keeps this design's record-sleeve layout (recent and top tracks with album art, genre estimates on request, a reflection). The unused mood chart and listening-pattern code was removed.
- `assets/innerbloom.css` holds the styles for these views and the restyled components. Storage keys and page events use the `innerbloom.` prefix; environment variables use `INNERBLOOM_`.

The design-prototype files and the earlier mockup screenshots have been removed. The README now shows the product video and animations in `docs/media/`, rendered from `docs/media/src` by `scripts/build_readme_media.py`.

Verification after the merge: 89 backend checks and four UI-serving tests pass. In the demo preview, Write (with the month-ago pill), Conversations (voice picker and a streamed reply), Insights, Memory map, People (cards, detail drawer, adding a note) and Settings (notifications) were checked at 1440px with a clear console; People was also checked at 390px with no horizontal overflow. Live Ollama, Spotify login and dictation were not exercised after the merge.
