// The web app's themes, in the order t and the header button cycle through them. The server keeps the
// same list (mason.server.context.THEMES) to check the per-user theme setting.
export const THEMES = ['bricks', 'mortar']
// The light or dark theme of the shared BitsAndBricks tokens each one sits on (data-theme on <html>).
export const SCHEME = { bricks: 'dark', mortar: 'light' }
