import * as d3 from 'd3';
import { LAND, poly } from './land';
import { t, type Lang } from './i18n';

interface PortProps {
  name: string;
  member_since: number;
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

const LABELLED = ['Bergen', 'Reykjavík', 'Kirkwall', 'Tromsø', 'Oslo', 'Trondheim'];

function distBars(dist: number[]): string {
  const maxBand = Math.max(...dist);
  return dist
    .map((v, i) => {
      const cls = i === 3 ? 'hi' : i === 2 ? 'mid' : '';
      return `<div class="${cls}" style="height:${Math.round((v / maxBand) * 100)}%"></div>`;
    })
    .join('');
}

export async function initMapApp(root: HTMLElement) {
  const lang = (root.dataset.lang as Lang) || 'no';
  const nf = () => new Intl.NumberFormat(lang === 'no' ? 'nb-NO' : 'en-GB');

  const svg = d3.select<SVGSVGElement, unknown>(root.querySelector('#map')!);
  const statBand = root.querySelector('#statBand')!;
  const panel = root.querySelector('#portPanel')!;

  const [summary, ports]: [Summary, PortCollection] = await Promise.all([
    fetch('/api/summary.json').then((r) => r.json()),
    fetch('/api/ports.geojson').then((r) => r.json()),
  ]);

  let selected: PortFeature | null = null;

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

  function drawMap() {
    svg.selectAll('*').remove();
    const node = svg.node()!;
    const w = node.clientWidth;
    const h = node.clientHeight;
    const projection = d3.geoMercator().fitExtent(
      [
        [24, 20],
        [w - 24, h - 20],
      ],
      { type: 'FeatureCollection', features: [poly([[-26, 55], [33, 55], [33, 71.5], [-26, 71.5], [-26, 55]])] } as any
    );
    const path = d3.geoPath(projection as any);

    const grat = d3.geoGraticule().step([5, 5]);
    svg
      .append('path')
      .attr('d', path(grat() as any))
      .attr('fill', 'none')
      .attr('stroke', '#C9C4B4')
      .attr('stroke-opacity', 0.45)
      .attr('stroke-width', 0.6)
      .attr('stroke-dasharray', '1 4');

    svg
      .append('g')
      .selectAll('path')
      .data(LAND.features)
      .join('path')
      .attr('d', path as any)
      .attr('fill', 'var(--sjo)')
      .attr('stroke', 'var(--blekk)')
      .attr('stroke-width', 1.1);

    const g = svg.append('g');
    const dots = g
      .selectAll<SVGGElement, PortFeature>('g.port')
      .data(ports.features)
      .join('g')
      .attr('class', 'port')
      .attr('transform', (d) => `translate(${projection(d.geometry.coordinates as [number, number])})`);

    dots
      .filter((d) => d === selected)
      .append('circle')
      .attr('r', 10)
      .attr('fill', 'none')
      .attr('stroke', 'var(--blekk)')
      .attr('stroke-width', 1);

    dots
      .append('circle')
      .attr('class', 'port-dot')
      .attr('r', (d) => (d === selected ? 6.5 : 5))
      .attr('fill', 'var(--gronn)')
      .attr('stroke', 'var(--papir)')
      .attr('stroke-width', 1.2)
      .on('mouseover', function () {
        d3.select(this).attr('r', 6.5);
      })
      .on('mouseout', function (_e, d) {
        d3.select(this).attr('r', d === selected ? 6.5 : 5);
      })
      .on('click', (_e, d) => {
        selected = d;
        drawMap();
        renderPanel(d);
      });

    dots
      .filter((d) => LABELLED.includes(d.properties.name) || d === selected)
      .append('text')
      .attr('class', 'port-label')
      .attr('y', 20)
      .attr('text-anchor', 'middle')
      .text((d) => d.properties.name);
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
      <div class="since">${t(lang, 'pp_since')} ${pr.member_since}</div>
      ${panelRows(pr)}`;
    panel.querySelector('#ppBack')?.addEventListener('click', () => {
      selected = null;
      drawMap();
      renderPanel(null);
    });
  }

  window.addEventListener('resize', drawMap);
  renderStats();
  drawMap();
  renderPanel(selected);
}
