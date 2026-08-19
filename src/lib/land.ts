// Simplified illustrative coastlines only. TODO (handoff.md #5): replace with
// Natural Earth 1:50m via MapLibre, or keep D3 and swap this data source.
import { geoArea } from 'd3';

// d3-geo reads ring winding via the spherical right-hand rule: get it
// backwards and geoArea/geoBounds return the *complement* of the intended
// shape (the rest of the globe) instead of the small polygon itself. Detect
// and correct that here so callers can list rings in whichever order.
export function poly(ring: [number, number][]) {
  const feature = { type: 'Feature' as const, geometry: { type: 'Polygon' as const, coordinates: [ring] } };
  if (geoArea(feature) > 2 * Math.PI) {
    feature.geometry.coordinates = [ring.slice().reverse()];
  }
  return feature;
}

export const LAND = {
  type: 'FeatureCollection' as const,
  features: [
    poly([[4.9,58.4],[5.3,59.0],[5.1,59.8],[4.9,61.0],[5.5,61.9],[6.4,62.4],[7.5,63.0],[9.5,63.7],[11.0,64.7],[12.4,65.8],[13.7,66.8],[15.5,67.8],[17.5,68.7],[19.5,69.5],[22.0,70.0],[25.5,70.9],[28.5,71.1],[31.5,70.4],[33.0,69.8],[33.0,55.6],[12.8,55.4],[11.2,57.9],[10.7,59.9],[10.2,59.1],[9.4,58.9],[8.0,58.1],[6.5,58.1],[4.9,58.4]]),
    poly([[-24.5,65.0],[-23.2,66.0],[-21.5,66.2],[-18.8,66.4],[-16.2,66.3],[-14.5,65.8],[-13.6,65.1],[-14.3,64.4],[-16.0,63.8],[-18.7,63.4],[-21.0,63.5],[-22.7,63.9],[-22.5,64.5],[-24.5,65.0]]),
    poly([[-5.8,58.6],[-5.0,58.6],[-3.5,58.6],[-3.0,57.7],[-2.0,57.6],[-1.8,56.6],[-2.6,56.0],[-3.2,55.7],[-4.9,54.7],[-6.2,55.3],[-5.6,56.5],[-6.4,57.3],[-5.9,57.9],[-5.8,58.6]]),
    poly([[-3.4,58.9],[-2.7,58.95],[-2.6,59.15],[-3.1,59.25],[-3.4,58.9]]),
    poly([[-1.4,59.9],[-1.0,60.05],[-1.1,60.55],[-1.5,60.4],[-1.4,59.9]]),
    poly([[-7.3,61.9],[-6.6,62.0],[-6.8,62.35],[-7.3,61.9]]),
  ],
};
