# Roadmap

Ordered by what unblocks the most.

## Next: verify on the real target
1. Merge with the Phase 0 work from the Mac (not yet pushed to GitHub).
2. Run the installer and all test suites on Ubuntu 24.04 ARM64 in UTM (TESTING.md).
3. First live run with an API key: the example instructions from the brief.
4. Verify window control, input automation, AT-SPI, voice with real hardware.

## Then: gaps in the build
- Browser automation inside pages (Playwright session: tabs, click, type). Today
  TITAN opens/searches in your browser and can read public pages, but cannot
  drive a page.
- Summarising PDFs and office documents (today: text files and web pages).
- Automatic conversation summaries into memory.
- Changing display, network and Bluetooth settings (today: status only; volume
  and colour scheme can be changed).
- Dedicated wake-word detector instead of chunked transcription.
- Per-plugin enable/disable UI for individual permissions; out-of-process,
  sandboxed plugins.
- In-app code editor (today: opens your editor, files and terminal).
- Electron or GNOME Shell extension packaging; full session (`titan.desktop`
  session file) rather than an autostarted window.
- Screen understanding (screenshots to the model) for apps without accessibility data.

## Hardening
- Performance and load testing; long-run stability of the wake-word loop.
- Independent security review of the classifier and approval flow.
- `.deb` packaging and CI on ARM64.
