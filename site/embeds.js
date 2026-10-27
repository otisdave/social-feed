export function safeHttps(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password) {
    throw new Error('Le lien de cette publication est invalide.');
  }
  return url;
}

export function embedHelp(embed) {
  const provider = embed.kind === 'facebook' ? 'Facebook' : 'YouTube';
  const symptom = embed.isVideo ? 'Cadre gris, blanc ou lecture bloquée ?' : 'Cadre gris, blanc ou icône 🚫 ?';
  return `${symptom} ${provider} peut être bloqué par la prévention du suivi du navigateur, une extension ou ses propres restrictions. Sous Edge, l’icône à gauche de l’adresse indique les éléments bloqués (prévention du suivi « Stricte »). Sous Firefox, consultez le bouclier près de l’adresse. Le contenu archivé reste affiché ci-dessous. Vous pouvez fermer le lecteur ou ouvrir la source officielle sans modifier vos protections.`;
}

export function embedFor(item, { width = 500 } = {}) {
  const official = safeHttps(item.url);
  if (item.platform === 'youtube' && official.hostname === 'www.youtube.com') {
    const videoId = official.searchParams.get('v');
    if (!/^[\w-]{11}$/.test(videoId || '')) return null;
    return {
      url: `https://www.youtube-nocookie.com/embed/${videoId}`,
      kind: 'youtube',
      isVideo: true,
      privacy: 'Ce lecteur contacte YouTube dès son chargement et lui transmet votre adresse IP. La lecture démarre avec le bouton ▶ du lecteur.',
    };
  }
  if (item.platform === 'facebook' && official.hostname === 'www.facebook.com') {
    const isVideo = /\/(?:reel|videos)\//.test(official.pathname);
    const url = new URL(`https://www.facebook.com/plugins/${isVideo ? 'video' : 'post'}.php`);
    url.searchParams.set('href', official.href);
    url.searchParams.set('show_text', 'true');
    url.searchParams.set('width', String(Math.max(220, Math.min(500, Math.round(width)))));
    return {
      url: url.href,
      kind: 'facebook',
      isVideo,
      privacy: isVideo
        ? 'Ce lecteur contacte Facebook dès son chargement et lui transmet votre adresse IP. Facebook peut utiliser des cookies ou demander une connexion. La lecture démarre avec le bouton ▶ du lecteur.'
        : 'Cette publication Facebook intégrée contacte Facebook dès son chargement et lui transmet votre adresse IP. Facebook peut utiliser des cookies ou demander une connexion.',
    };
  }
  return null;
}

export function createEmbed(embed, title, onError) {
  const iframe = document.createElement('iframe');
  iframe.src = embed.url;
  iframe.loading = 'lazy';
  iframe.title = title;
  iframe.className = `publication-embed ${embed.kind}`;
  iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen';
  iframe.allowFullscreen = true;
  iframe.referrerPolicy = 'strict-origin-when-cross-origin';
  iframe.addEventListener('error', onError);
  return iframe;
}
