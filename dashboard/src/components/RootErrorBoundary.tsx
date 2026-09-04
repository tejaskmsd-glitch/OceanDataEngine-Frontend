import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Catches render errors so a single failing view never blanks the whole app. */
export class RootErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface to the console for local debugging; no external telemetry.
    console.error('Dashboard render error:', error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div style={{ padding: '2rem', maxWidth: 640, margin: '0 auto' }}>
          <div className="state-panel state-panel--error" role="alert">
            <h1 style={{ fontSize: 18 }}>Something went wrong</h1>
            <p className="mono">{this.state.error.message}</p>
            <button type="button" className="btn" onClick={() => window.location.reload()}>
              Reload dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
