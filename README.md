# Echo — Releases

Offizielle Download- und Auto-Update-Distribution für **Echo** (Subunit).

Dieses Repository enthält kompilierte Installer und das Updater-Manifest
(`latest.json`). Der Quellcode ist proprietär und nicht Teil dieses Repositories.

**Downloads:** [Releases](../../releases/latest) — macOS (Apple Silicon), Windows x64, Windows ARM64, Linux x86_64.

**Auto-Update-Feed:** `https://github.com/subunit-ai/echo-releases/releases/latest/download/latest.json`

Echo-Releases enthalten ausschließlich die Diktat-Engine (`local-whisper` bzw.
`local-whisper-gpu`). Meeting-Aufzeichnung, Diarisierung und Voiceprints gehören
zum eigenständigen SCAI-Meet-Plugin und sind kein Echo-Releasebestandteil mehr.

Automatische Poller bauen ausschließlich suffixlose Stable-Tags wie `v0.5.166`;
dieser Kanal veröffentlicht weiterhin atomar als normalen GitHub-`Latest` und
speist Echos Standard-Updater.

Manuelle Builds, Poller und externe Dispatches teilen ein workflowweites
Release-Schloss. Überschneiden sich zwei Trigger, wartet der spätere Lauf bis zum
vollständigen Publish und wird anschließend zum No-op; Assets und Publish-Job
können dadurch nie parallel auf denselben Draft zugreifen.

Ein signierter Testkandidat kann ausschließlich manuell mit `release_mode=draft_rc`
und einem exakt passenden Tag wie `v0.5.166-rc.1` gebaut werden. Er bleibt als
nicht öffentlich gelisteter GitHub-Draft mit gesetztem Prerelease-Merkmal bestehen
und wird niemals `Latest`. Dadurch kann er von einem Maintainer geprüft und manuell
installiert werden, ohne reguläre Echo-Installationen zu aktualisieren.

Vor jedem Publish beziehungsweise RC-Abschluss verifiziert der Workflow die vier
Updater-Artefakte und ihre vier `.sig`-Dateien kryptografisch gegen den Public Key
der exakt gebauten Echo-Quelle. IDs und SHA-256-Werte aller acht Dateien werden bis
zur finalen Publish-Entscheidung gebunden. Ab Version 1.0 einschließlich Release
Candidates kommt die native Plattform-Trust-Prüfung für macOS und Windows hinzu.
Die öffentlichen Signer-Identitäten, Prüfungen und noch fehlenden externen
Voraussetzungen stehen in [`docs/PLATFORM-TRUST.md`](docs/PLATFORM-TRUST.md).

© Subunit. Alle Rechte vorbehalten.
