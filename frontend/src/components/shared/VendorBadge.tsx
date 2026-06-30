interface Props {
  vendor: string | null;
  category?: string | null;
  size?: "sm" | "md";
}

const CATEGORY_ICONS: Record<string, string> = {
  pbx: "🖥",
  phone: "☎",
  softphone: "💻",
};

export default function VendorBadge({ vendor, category, size = "sm" }: Props) {
  if (!vendor) return null;

  const icon = category ? CATEGORY_ICONS[category] ?? "" : "";

  return (
    <span
      className={`vendor-badge ${size === "sm" ? "vendor-badge-sm" : ""}`}
      title={category ? `${vendor} (${category})` : vendor}
    >
      {icon && <span className="vendor-icon">{icon}</span>}
      {vendor}
    </span>
  );
}
