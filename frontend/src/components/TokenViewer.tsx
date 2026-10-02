import React from 'react';
import type { LexerStage } from '../types/pipeline';

interface TokenViewerProps {
  lexer: LexerStage;
}

export const TokenViewer: React.FC<TokenViewerProps> = ({ lexer }) => {
  if (lexer.status === 'ERROR' && lexer.error) {
    return (
      <div className="error-banner">
        <div className="error-banner-title">
          <span>✗ Lexical Error</span>
          {lexer.error.line !== undefined && (
            <span>[Line {lexer.error.line}, Col {lexer.error.col}]</span>
          )}
        </div>
        <p>{lexer.error.message}</p>
      </div>
    );
  }

  if (lexer.status === 'NOT_RUN' || !lexer.tokens) {
    return <div style={{ color: 'var(--text-muted)' }}>Lexer has not run yet. Execute a query to inspect tokens.</div>;
  }

  const getTypeBadgeClass = (type: string) => {
    switch (type) {
      case 'KEYWORD':
        return 'info'; // Subtle violet
      case 'IDENTIFIER':
        return 'neutral'; // Clean glass
      case 'NUMBER':
      case 'STRING':
        return 'warning'; // Subtle amber
      case 'OPERATOR':
        return 'secondary'; // Subtle magenta
      default:
        return 'neutral';
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
        <p style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
          Input query stream decomposed into typed lexical tokens by <code className="mono">backend.lexer.Lexer</code>
        </p>
        <span className="badge-tag info">Total Tokens: {lexer.token_count || lexer.tokens.length}</span>
      </div>

      <div className="data-table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '50px' }}>#</th>
              <th style={{ width: '160px' }}>Token Type</th>
              <th>Lexeme Value</th>
              <th style={{ width: '80px', textAlign: 'center' }}>Line</th>
              <th style={{ width: '80px', textAlign: 'center' }}>Column</th>
            </tr>
          </thead>
          <tbody>
            {lexer.tokens.map((tok) => (
              <tr key={tok.index}>
                <td style={{ color: 'var(--text-muted)' }}>{tok.index}</td>
                <td>
                  <span className={`badge-tag ${getTypeBadgeClass(tok.type)}`}>
                    {tok.type}
                  </span>
                </td>
                <td>
                  <code className="mono" style={{ color: '#0f172a', fontWeight: 600 }}>
                    {tok.value === '' && tok.type === 'EOF' ? '⟨EOF⟩' : tok.value}
                  </code>
                </td>
                <td style={{ textAlign: 'center', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{tok.line}</td>
                <td style={{ textAlign: 'center', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{tok.col}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
