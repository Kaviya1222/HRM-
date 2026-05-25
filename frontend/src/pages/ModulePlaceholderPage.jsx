import { Clock, ArrowRight } from "lucide-react";
import * as LucideIcons from "lucide-react";

function ModulePlaceholderPage({ title, description, highlights = [], icon = "Clock" }) {
  const Icon = LucideIcons[icon] || Clock;

  return (
    <div className="page-container">
      <div className="module-coming-soon">
        <div className="module-cs-icon">
          <Icon size={32} />
        </div>
        <h2 className="module-cs-title">{title}</h2>
        <p className="module-cs-desc">{description}</p>

        <div className="module-cs-features">
          {highlights.map((item) => (
            <div className="module-cs-feature" key={item}>
              <ArrowRight size={14} className="module-cs-arrow" />
              <span>{item}</span>
            </div>
          ))}
        </div>

        <div className="module-cs-badge">Coming Soon</div>
      </div>
    </div>
  );
}

export default ModulePlaceholderPage;
