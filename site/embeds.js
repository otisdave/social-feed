export function safeHttps(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password) {
    throw new Error('Le lien de cette publication est invalide.');
  }
  return url;
}

export function embedFor(item, { autoplay = false, width = 500 } = {}) {
  const official = safeHttps(item.url);
  if (item.platform === 'youtube' && official.hostname === 'www.youtube.com') {
    const videoId = official.searchParams.get('v');
    if (!/^[\w-]{11}$/.test(videoId || '')) return null;
    return {
      url: `https://www.youtube-nocookie.com/embed/${videoId}${autoplay ? '?autoplay=1' : ''}`,
      kind: 'youtube',
      isVideo: true,
      label: 'Charger le lecteur YouTube',
      privacy: 'Au clic, YouTube reçoit votre adresse IP et peut utiliser des données de navigation.',
    };
  }
  if (item.platform === 'facebook' && official.hostname === 'www.facebook.com') {
    const isVideo = /\/(?:reel|videos)\//.test(official.pathname);
    const url = new URL(`https://www.facebook.com/plugins/${isVideo ? 'video' : 'post'}.php`);
    url.searchParams.set('href', official.href);
    url.searchParams.set('show_text', 'true');
    url.searchParams.set('width', String(Math.max(220, Math.min(500, Math.round(width)))));
    if (autoplay && isVideo) url.searchParams.set('autoplay', 'true');
    return {
      url: url.href,
      kind: 'facebook',
      isVideo,
      label: 'Afficher la publication Facebook',
      privacy: 'Au clic, Facebook reçoit votre adresse IP et peut utiliser des cookies ou demander une connexion.',
    };
  }
  return null;
}

export function createEmbed(embed, title, onError) {
  const iframe = document.createElement('iframe');
  iframe.src = embed.url;
  iframe.title = title;
  iframe.className = `publication-embed ${embed.kind}`;
  iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen';
  iframe.allowFullscreen = true;
  iframe.referrerPolicy = 'strict-origin-when-cross-origin';
  iframe.addEventListener('error', onError);
  return iframe;
}
