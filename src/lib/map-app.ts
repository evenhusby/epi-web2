import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';
import { t, type Lang } from './i18n';

interface PortProps {
  name: string;
  calls_ytd: number;
  avg_score: number;
  ops_share_pct: number;
  nox_reduced_ytd: number;
  score_distribution: [number, number, number, number];
}

type PortFeature = GeoJSON.Feature<GeoJSON.Point, PortProps>;
type PortCollection = GeoJSON.FeatureCollection<GeoJSON.Point, PortProps>;

interface Summary {
  active_ports: number;
  port_calls_ytd: number;
  sox_reduced_tonnes_ytd: number;
  nox_reduced_tonnes_ytd: number;
}

// Always-labelled ports; the selected port (if any) is added on top of this.
const LABELLED = ['Bergen', 'Reykjavík', 'Kirkwall', 'Tromsø', 'Oslo', 'Trondheim'];

// Design tokens (src/styles/global.css) duplicated here as literals -- Mapbox
// GL paint/layout properties can't read CSS custom properties.
const COLOR_GRONN = '#1E5C48';
const COLOR_PAPIR = '#FDFCF9';
const COLOR_BLEKK = '#26332F';

// light-v11 layers that read as visual noise against the editorial design
// (streets/POI/transit/building clutter). Hides anything whose id matches.
// This is a blunt first pass, not a substitute for a proper custom Mapbox
// Studio style matching the ink/paper palette exactly -- revisit if the
// look needs to be tighter than this gets it.
const NOISY_LAYER_PATTERN = /poi|transit|building|road-label|road-number|road-exit|path-pedestrian|contour|hillshade|natural-line-label|water-line-label|water-point-label/i;

function distBars(dist: number[]): string {
  const maxBand = Math.max(...dist);
  return dist
    .map((v, i) => {
      const cls = i === 3 ? 'hi' : i === 2 ? 'mid' : '';
      return `<div class="${cls}" style="height:${Math.round((v / maxBand) * 100)}%"></div>`;
    })
    .join('');
}

function simplifyBaseStyle(map: mapboxgl.Map) {
  for (const layer of map.getStyle()?.layers ?? []) {
    if (NOISY_LAYER_PATTERN.test(layer.id)) {
      map.setLayoutProperty(layer.id, 'visibility', 'none');
    }
  }
}

export async function initMapApp(root: HTMLElement) {
  const lang = (root.dataset.lang as Lang) || 'no';
  const nf = () => new Intl.NumberFormat(lang === 'no' ? 'nb-NO' : 'en-GB');

  const mapContainer = root.querySelector<HTMLElement>('#map')!;
  const statBand = root.querySelector('#statBand')!;
  const panel = root.querySelector('#portPanel')!;

  const [summary, ports]: [Summary, PortCollection] = await Promise.all([
    fetch('/api/summary.json').then((r) => r.json()),
    fetch('/api/ports.geojson').then((r) => r.json()),
  ]);

  let selected: PortFeature | null = null;
  let hovered: PortFeature | null = null;

  function renderStats() {
    statBand.innerHTML = `
      <div class="stat"><div class="value">${summary.active_ports}</div><div class="label">${t(lang, 'stat_ports')}</div></div>
      <div class="stat"><div class="value">${nf().format(summary.port_calls_ytd)}</div><div class="label">${t(lang, 'stat_calls')}</div></div>
      <div class="stat"><div class="value green">${summary.sox_reduced_tonnes_ytd} <span class="unit">${t(lang, 'tonnes')}</span></div><div class="label">${t(lang, 'stat_sox')}</div></div>
      <div class="stat"><div class="value green">${nf().format(summary.nox_reduced_tonnes_ytd)} <span class="unit">${t(lang, 'tonnes')}</span></div><div class="label">${t(lang, 'stat_nox')}</div></div>`;
  }

  function aggregateAll() {
    const fs = ports.features;
    const totalCalls = fs.reduce((s, f) => s + f.properties.calls_ytd, 0);
    const wScore = fs.reduce((s, f) => s + f.properties.avg_score * f.properties.calls_ytd, 0) / totalCalls;
    const wOps = fs.reduce((s, f) => s + f.properties.ops_share_pct * f.properties.calls_ytd, 0) / totalCalls;
    const dist = [0, 0, 0, 0];
    fs.forEach((f) => f.properties.score_distribution.forEach((v, i) => (dist[i] += v)));
    return {
      calls_ytd: summary.port_calls_ytd,
      avg_score: wScore,
      ops_share_pct: Math.round(wOps),
      nox_reduced_ytd: summary.nox_reduced_tonnes_ytd,
      score_distribution: dist,
    };
  }

  function panelRows(a: { calls_ytd: number; avg_score: number; ops_share_pct: number; nox_reduced_ytd: number; score_distribution: number[] }) {
    return `
      <div class="pp-row"><span class="k">${t(lang, 'pp_calls')}</span><span class="v">${nf().format(a.calls_ytd)}</span></div>
      <div class="pp-row"><span class="k">${t(lang, 'pp_score')}</span><span class="v">${a.avg_score.toFixed(1)}</span></div>
      <div class="pp-row"><span class="k">${t(lang, 'pp_ops')}</span><span class="v">${a.ops_share_pct} <small>%</small></span></div>
      <div class="pp-row"><span class="k">${t(lang, 'pp_nox')}</span><span class="v">${nf().format(a.nox_reduced_ytd)} <small>${t(lang, 'tonnes')}</small></span></div>
      <div class="dist-title">${t(lang, 'pp_dist')}</div>
      <div class="dist-bars">${distBars(a.score_distribution)}</div>
      <div class="dist-axis"><span>0–30</span><span>30–50</span><span>50–70</span><span>70–100</span></div>`;
  }

  function renderPanel(f: PortFeature | null) {
    if (!f) {
      const a = aggregateAll();
      panel.innerHTML = `
        <div class="pp-eyebrow">${t(lang, 'pp_eyebrow')}</div>
        <h3>${t(lang, 'pp_all')}</h3>
        <div class="since">${summary.active_ports} ${t(lang, 'pp_all_sub')}</div>
        ${panelRows(a)}
        <div class="pp-hint">${t(lang, 'pp_hint')}</div>`;
      return;
    }
    const pr = f.properties;
    panel.innerHTML = `
      <button type="button" class="pp-back" id="ppBack">${t(lang, 'pp_back')}</button>
      <div class="pp-eyebrow">${t(lang, 'pp_eyebrow')}</div>
      <h3>${pr.name}</h3>
      ${panelRows(pr)}`;
    panel.querySelector('#ppBack')?.addEventListener('click', () => select(null));
  }

  renderStats();

  const token = import.meta.env.PUBLIC_MAPBOX_TOKEN as string | undefined;
  if (!token) {
    mapContainer.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--grafitt);font-size:13px;text-align:center;padding:0 20px;">Map unavailable: PUBLIC_MAPBOX_TOKEN is not set.</div>`;
    console.warn('PUBLIC_MAPBOX_TOKEN is not set -- see .env.example.');
    renderPanel(null);
    return;
  }

  mapboxgl.accessToken = token;

  const bounds = ports.features.reduce(
    (b, f) => b.extend(f.geometry.coordinates as [number, number]),
    new mapboxgl.LngLatBounds()
  );

  // Fitting to `bounds` at construction time is unreliable if the container
  // hasn't been laid out yet (e.g. web fonts still loading) -- Mapbox can't
  // compute a valid initial camera/tile matrix, logs "Map cannot fit within
  // canvas...", and never recovers (no tiles are ever requested, even after
  // the container gets its real size). Construct with a fixed fallback view,
  // then resize + fitBounds explicitly once the container is guaranteed to
  // have real dimensions (on 'load').
  const map = new mapboxgl.Map({
    container: mapContainer,
    style: 'mapbox://styles/mapbox/light-v11',
    center: [0, 55],
    zoom: 2,
    attributionControl: false,
  });
  map.on('error', (e) => console.error('MAPBOX ERROR', (e as any)?.error?.message || e));
  map.addControl(new mapboxgl.AttributionControl({ compact: true }));
  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right');

  // Defensive: the canvas's WebGL viewport is sized from the container's
  // dimensions at construction time, which can be stale in a CSS grid
  // column if layout hasn't fully settled yet. Watching the real container
  // size and resizing whenever it changes is more robust than a single
  // point-in-time resize() call, even though the specific "blank basemap"
  // bug reported in this session turned out to be an invalid Mapbox token,
  // not a layout-timing issue.
  let lastSize = '';
  const resizeObserver = new ResizeObserver(() => {
    const { width, height } = mapContainer.getBoundingClientRect();
    const key = `${width}x${height}`;
    if (width > 0 && height > 0 && key !== lastSize) {
      lastSize = key;
      map.resize();
      map.triggerRepaint();
    }
  });
  resizeObserver.observe(mapContainer);

  function labelFilter(): mapboxgl.FilterSpecification {
    const names = [...LABELLED];
    if (selected) names.push(selected.properties.name);
    if (hovered) names.push(hovered.properties.name);
    return ['in', ['get', 'name'], ['literal', names]];
  }

  function select(f: PortFeature | null) {
    if (selected) {
      map.setFeatureState({ source: 'ports', id: selected.properties.name }, { selected: false });
    }
    selected = f;
    if (selected) {
      map.setFeatureState({ source: 'ports', id: selected.properties.name }, { selected: true });
    }
    if (map.getLayer('ports-labels')) {
      map.setFilter('ports-labels', labelFilter());
    }
    renderPanel(selected);
  }

  map.on('load', () => {
    map.resize();
    map.fitBounds(bounds, { padding: 48, animate: false });
    simplifyBaseStyle(map);

    map.addSource('ports', {
      type: 'geojson',
      data: ports,
      promoteId: 'name',
    });

    map.addLayer({
      id: 'ports-circles',
      type: 'circle',
      source: 'ports',
      paint: {
        'circle-radius': ['case', ['boolean', ['feature-state', 'selected'], false], 6.5, 5],
        'circle-color': COLOR_GRONN,
        'circle-stroke-color': COLOR_PAPIR,
        'circle-stroke-width': ['case', ['boolean', ['feature-state', 'selected'], false], 2, 1.2],
      },
    });

    map.addLayer({
      id: 'ports-labels',
      type: 'symbol',
      source: 'ports',
      filter: labelFilter(),
      layout: {
        'text-field': ['get', 'name'],
        'text-size': 12,
        'text-offset': [0, 1.2],
        'text-anchor': 'top',
      },
      paint: {
        'text-color': COLOR_BLEKK,
        'text-halo-color': COLOR_PAPIR,
        'text-halo-width': 1.4,
      },
    });

    map.on('mousemove', 'ports-circles', (e) => {
      map.getCanvas().style.cursor = 'pointer';
      const feature = e.features?.[0] as unknown as PortFeature | undefined;
      if (feature && feature.properties.name !== hovered?.properties.name) {
        hovered = feature;
        map.setFilter('ports-labels', labelFilter());
      }
    });
    map.on('mouseleave', 'ports-circles', () => {
      map.getCanvas().style.cursor = '';
      if (hovered) {
        hovered = null;
        map.setFilter('ports-labels', labelFilter());
      }
    });
    map.on('click', 'ports-circles', (e) => {
      const feature = e.features?.[0] as unknown as PortFeature | undefined;
      if (feature) select(feature);
    });

    renderPanel(selected);
    map.resize();
    map.triggerRepaint();
  });
}
