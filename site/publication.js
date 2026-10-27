import { safeHttps, embedFor, createEmbed } from './embeds.js';

const byId = (id) => document.getElementById(id);

function activateEmbed(embed, title) {
  const iframe = createEmbed(embed, title, () => {
    byId('embed-fallback').textContent = 'Le contenu intégré n’a pas pu être chargé. Utilisez le bouton vers la source officielle.';
  });
  byId('embed-container').replaceChildren(iframe);
  byId('activate-embed').hidden = true;
  byId('preview').hidden = true;
  byId('embed-fallback').hidden = false;
}

async function loadPublication() {
  try {
    const params = new URLSearchParams(location.search);
    const source = params.get('source');
    const id = params.get('id');
    if (!source || !id) throw new Error('Ce lien ne désigne aucune publication.');
    const response = await fetch('./feed.json', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Le serveur a répondu HTTP ${response.status}.`);
    const feed = await response.json();
    if (feed.version !== 1 || !Array.isArray(feed.items)) throw new Error('Le format du fil est invalide.');
    const item = feed.items.find((entry) => entry.source_id === source && entry.id === id);
    if (!item) throw new Error('Cette publication est introuvable ou sa source a été retirée du fil.');
    for (const field of ['title', 'source_name', 'platform', 'description']) {
      if (typeof item[field] !== 'string') throw new Error('Le format de cette publication est invalide.');
    }
    const published = new Date(item.published_at);
    if (!Number.isFinite(published.getTime())) throw new Error('La date de cette publication est invalide.');
    const official = safeHttps(item.url);
    document.title = `${item.title} — Social Feed`;
    byId('publication-title').textContent = item.title;
    byId('publication-source').textContent = `${item.source_name} · ${item.platform}`;
    byId('publication-date').dateTime = item.published_at;
    byId('publication-date').textContent = new Intl.DateTimeFormat('fr-CA', {
      dateStyle: 'long', timeStyle: 'short',
    }).format(published);
    byId('official-link').href = official.href;
    byId('publication-description').textContent = item.description || 'Aucun texte archivé pour cette publication.';
    byId('excerpt-note').hidden = item.platform !== 'facebook';
    if (item.image_url) {
      const image = byId('publication-image');
      image.src = safeHttps(item.image_url).href;
      image.addEventListener('error', () => { byId('preview').hidden = true; }, { once: true });
      byId('preview').hidden = false;
    }
    const embed = embedFor(item);
    if (embed) {
      byId('embed-section').hidden = false;
      byId('activate-embed').textContent = embed.label;
      byId('embed-privacy').textContent = embed.privacy;
      byId('activate-embed').addEventListener('click', () => activateEmbed(embed, item.title), { once: true });
    }
    byId('detail').hidden = false;
  } catch (error) {
    console.error('Unable to load publication:', error);
    byId('publication-error').textContent = `Impossible d’afficher cette publication. ${error.message}`;
    byId('publication-error').hidden = false;
  } finally {
    byId('loading').hidden = true;
    byId('publication').setAttribute('aria-busy', 'false');
  }
}

loadPublication();
