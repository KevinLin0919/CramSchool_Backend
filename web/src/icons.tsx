// Stroke icons, drawn inline so they take the text colour.
const P = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export const Icon = {
  overview: () => (<svg width="17" height="17" viewBox="0 0 24 24" {...P}><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></svg>),
  exam: () => (<svg width="17" height="17" viewBox="0 0 24 24" {...P}><path d="M6 3h9l4 4v14H6z" /><path d="M9 12h7M9 16h5" /></svg>),
  student: () => (<svg width="17" height="17" viewBox="0 0 24 24" {...P}><circle cx="12" cy="8" r="4" /><path d="M4 21c1-4 4-6 8-6s7 2 8 6" /></svg>),
  trend: () => (<svg width="17" height="17" viewBox="0 0 24 24" {...P}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></svg>),
  search: () => (<svg width="15" height="15" viewBox="0 0 24 24" {...P} stroke="#85918a"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>),
  sparkle: ({ color = "#ffffff", size = 16 }: { color?: string; size?: number }) => (<svg width={size} height={size} viewBox="0 0 24 24" {...P} stroke={color}><path d="M12 3l1.8 4.6L18 9.4l-4.2 1.8L12 16l-1.8-4.8L6 9.4l4.2-1.8z" /><path d="M19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></svg>),
  send: () => (<svg width="16" height="16" viewBox="0 0 24 24" {...P} stroke="#ffffff" strokeWidth={2.2}><path d="M5 12h14M13 6l6 6-6 6" /></svg>),
};
