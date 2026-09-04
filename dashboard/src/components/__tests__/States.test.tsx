import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AsyncBoundary, EmptyState, ErrorState } from '../States';

describe('AsyncBoundary', () => {
  it('shows error state with retry when not yet loaded', () => {
    const onRetry = vi.fn();
    render(
      <AsyncBoundary
        loading={false}
        loaded={false}
        error={new Error('nope')}
        data={null}
        onRetry={onRetry}
      >
        {() => <div>content</div>}
      </AsyncBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('nope');
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('shows loading skeleton before first load', () => {
    render(
      <AsyncBoundary loading loaded={false} error={null} data={null}>
        {() => <div>content</div>}
      </AsyncBoundary>,
    );
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('renders empty state when isEmpty is true', () => {
    render(
      <AsyncBoundary
        loading={false}
        loaded
        error={null}
        data={[]}
        isEmpty={(d) => d.length === 0}
        emptyMessage="nothing here"
      >
        {() => <div>content</div>}
      </AsyncBoundary>,
    );
    expect(screen.getByText('nothing here')).toBeInTheDocument();
  });

  it('renders children with loaded data', () => {
    render(
      <AsyncBoundary loading={false} loaded error={null} data={{ n: 1 }}>
        {(d) => <div>value {d.n}</div>}
      </AsyncBoundary>,
    );
    expect(screen.getByText('value 1')).toBeInTheDocument();
  });

  it('keeps showing content on background error after load', () => {
    render(
      <AsyncBoundary loading loaded error={new Error('bg')} data={{ n: 2 }}>
        {(d) => <div>value {d.n}</div>}
      </AsyncBoundary>,
    );
    // loaded=true takes precedence, so content stays visible during refetch errors
    expect(screen.getByText('value 2')).toBeInTheDocument();
  });
});

describe('EmptyState / ErrorState', () => {
  it('renders empty message', () => {
    render(<EmptyState>empty!</EmptyState>);
    expect(screen.getByText('empty!')).toBeInTheDocument();
  });

  it('renders error without retry button when no handler', () => {
    render(<ErrorState error={new Error('x')} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});
