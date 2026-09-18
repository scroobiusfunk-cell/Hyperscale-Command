export function Topbar({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  return (
    <header className="topbar">
      <div>
        <h1>{title}</h1>
        {subtitle ? <div className="topbar-sub">{subtitle}</div> : null}
      </div>
      {right}
    </header>
  );
}
