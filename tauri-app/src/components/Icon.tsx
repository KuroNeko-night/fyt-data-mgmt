interface IconProps {
  name: string;
  size?: number;
}

const paths: Record<string, string> = {
  home: "M3 10.8 12 3l9 7.8V21h-6v-6H9v6H3V10.8Z",
  calendar: "M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2Zm0 6h14M8 2v4m8-4v4",
  check: "M4 12.5 9.2 18 20 6",
  truck: "M3 6h11v11H3V6Zm11 4h4l3 4v3h-7v-7ZM7 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm11 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z",
  chart: "M4 20V10m6 10V4m6 16v-7m5 7H2",
  compare: "M7 7h13m0 0-4-4m4 4-4 4M17 17H4m0 0 4 4m-4-4 4-4",
  route: "M6 19a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm12-8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM8.5 14.5 15.5 9.5",
  database: "M4 6c0-2 3.6-3 8-3s8 1 8 3-3.6 3-8 3-8-1-8-3Zm0 0v6c0 2 3.6 3 8 3s8-1 8-3V6m-16 6v6c0 2 3.6 3 8 3s8-1 8-3v-6",
  tasks: "M8 6h12M8 12h12M8 18h12M3.5 6h.01M3.5 12h.01M3.5 18h.01",
  mapping: "M4 5h6v5H4V5Zm10 9h6v5h-6v-5ZM10 7.5h4a3 3 0 0 1 3 3V14",
  template: "M5 3h10l4 4v14H5V3Zm10 0v5h5M8 12h8m-8 4h8",
  invoice: "M6 3h12v18l-3-2-3 2-3-2-3 2V3Zm3 5h6m-6 4h6m-6 4h4",
  currency: "M6 4h12M12 4v16m-5-9h10m-10 5h10M7 4l5 7 5-7",
  rename: "M4 17.5V21h3.5L19 9.5 14.5 5 3 16.5l1 1Zm9-11 4.5 4.5",
  text: "M4 5h16M12 5v14M7 19h10",
  pdf: "M6 3h9l4 4v14H6V3Zm9 0v5h5M9 13h6m-6 4h5",
  excel: "M5 3h14v18H5V3Zm0 5h14M5 13h14M10 8v13",
  settings: "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm0-5v2m0 13v2m8.5-8.5h-2m-13 0h-2m15.3-6.3-1.4 1.4M7.1 16.9l-1.4 1.4m12.6 0-1.4-1.4M7.1 7.1 5.7 5.7",
  about: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-10v6m0-10h.01",
  collapse: "m14 7-5 5 5 5",
  panel: "M4 4h16v16H4V4Zm10 0v16",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-5v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4m0-12.8L17 7M7 17l-1.4 1.4",
  plus: "M12 5v14M5 12h14",
  folder: "M3 6h7l2 2h9v11H3V6Z",
  help: "M9.5 9a2.7 2.7 0 1 1 4.2 2.2c-1.1.8-1.7 1.3-1.7 2.8m0 4h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z",
};

export default function Icon({ name, size = 20 }: IconProps) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d={paths[name] ?? paths.about} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
