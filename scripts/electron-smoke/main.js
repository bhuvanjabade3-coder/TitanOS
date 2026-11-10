// Phase 0 smoke test: open a window, confirm it rendered, quit. Sandbox stays ON.
const { app, BrowserWindow } = require('electron');
app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 480, height: 240, backgroundColor: '#0E0F13',
    webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false } });
  win.webContents.once('did-finish-load', () => {
    console.log(`TITAN_SMOKE_OK electron ${process.versions.electron}`);
    setTimeout(() => app.quit(), 1500);
  });
  win.loadURL('data:text/html,<body style="margin:0;display:grid;place-items:center;height:100vh;background:%230E0F13;color:%238B5CF6;font:600 28px sans-serif">TITAN OS · smoke test</body>');
});
