declare module "leaflet" {
  const L: any;
  export default L;
}

declare module "react-leaflet" {
  export const MapContainer: any;
  export const Marker: any;
  export const Polyline: any;
  export const Popup: any;
  export const TileLayer: any;
  export function useMap(): any;
}
