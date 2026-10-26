# Third party notices

## video-use

Source: https://github.com/browser-use/video-use

Upstream commit: 43cfc566833548093455c9d4a46bd69913b7e552

Copyright (c) 2026 Browser Use. MIT License. Full license retained in `.agents/skills/video-use/LICENSE`. The bundled snapshot includes a local Windows subtitle path correction; see `patches/video-use-windows-subtitles.patch`. The snapshot may include its own supporting skill resources; they are retained together with their source.

## Standalone publisher

Adapted from the Zernio REST integration in the author's AI Video Pipeline repository, source commit `1c8b323fc581d280249111e8ed7563b1973aedb3`. No original account data or credentials are included. Internal distribution only; this notice does not grant a public license for the author's original code.

## motion-broll (motion-graphics)

Source: https://github.com/Barty-Bart/motion-graphics

Upstream commit: 3d83d987d658601d8a1269eb691622bdcd427335

Copyright (c) 2026 Bart. MIT License. Full license retained in `tools/vendor/motion-broll/LICENSE`. The bundled snapshot includes Windows-safe file URL and HTML path/encoding corrections; see `patches/motion-broll-windows-file-url.patch` and `patches/motion-broll-windows-pages.patch`. The Windows setup and video-use timeline bridge are kit-owned files outside that folder. Bundled Geist fonts are under the SIL Open Font License (`tools/vendor/motion-broll/engine/fonts/OFL-Geist.txt`); icon paths adapted from Lucide are ISC-licensed as documented upstream.

## Montserrat font (fitness explainer)

Source: https://github.com/google/fonts/tree/main/ofl/montserrat

Copyright 2024 The Montserrat.Git Project Authors. SIL Open Font License 1.1, retained in `tools/fitness/templates/fonts/OFL.txt`. Embedded unmodified in rendered scene pages.

## Dependencies and services

Python and npm dependencies retain their respective licenses, supplied by their packages at installation. FFmpeg, Git, Python, Node.js and Codex are installed separately and are not redistributed in the ZIP. ElevenLabs, Genmax, Google Gemini and Zernio are external services governed by their own terms, permissions, quotas and charges, including the commercial-use terms of generated voices and images. Playwright and Chromium for the fitness renderer are downloaded at setup into ignored folders, not bundled. No stock music, personal footage, browser profiles or authentication state is bundled.
