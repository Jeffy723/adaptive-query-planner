import React from 'react';
import type { ReactNode } from 'react';
import type { StageStatus } from '../types/pipeline';

interface CollapsibleSectionProps {
  id: string;
  stageNumber: number;
  title: string;
  subtitle?: string;
  status: StageStatus;
  statusText?: string;
  isExpanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  id,
  stageNumber,
  title,
  subtitle,
  status,
  statusText,
  isExpanded,
  onToggle,
  children,
}) => {
  const getBadgeClass = (s: StageStatus) => {
    switch (s) {
      case 'PASSED':
        return 'success';
      case 'ERROR':
        return 'danger';
      case 'RUNNING':
        return 'info';
      default:
        return 'neutral';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onToggle();
    }
  };

  return (
    <section
      id={id}
      className={`stage-section-card ${isExpanded ? 'is-expanded' : ''} ${status === 'ERROR' ? 'has-error' : ''}`}
    >
      <div
        className="stage-header"
        onClick={onToggle}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
      >
        <div className="stage-title-left">
          <span className="stage-num-badge">{stageNumber}</span>
          <span className="stage-name">{title}</span>
          {subtitle && <span className="stage-desc">— {subtitle}</span>}
        </div>
        <div className="stage-header-right">
          <span className={`badge-tag ${getBadgeClass(status)}`}>
            {statusText || status}
          </span>
          <span className="toggle-arrow">▼</span>
        </div>
      </div>
      {isExpanded && <div className="stage-content-body">{children}</div>}
    </section>
  );
};
