import { Button } from "@/components/ui/button";
import { AlertCircle } from "lucide-react";
import { Component, type ReactNode } from "react";

interface Props {
	children: ReactNode;
	fallback?: ReactNode;
}

interface State {
	hasError: boolean;
	error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
	constructor(props: Props) {
		super(props);
		this.state = { hasError: false };
	}

	static getDerivedStateFromError(error: Error): State {
		return {
			hasError: true,
			error,
		};
	}

	componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
		console.error("Error caught by boundary:", error, errorInfo);
	}

	render() {
		if (this.state.hasError) {
			if (this.props.fallback) {
				return this.props.fallback;
			}

			return (
				<div className="flex flex-col items-center justify-center p-4 space-y-4 text-center">
					<AlertCircle className="h-12 w-12 text-destructive" />
					<h2 className="text-lg font-semibold">Something went wrong</h2>
					<p className="text-sm text-muted-foreground max-w-md">
						{this.state.error?.message || "An unexpected error occurred"}
					</p>
					<Button
						variant="outline"
						onClick={() => this.setState({ hasError: false, error: undefined })}
					>
						Try again
					</Button>
				</div>
			);
		}

		return this.props.children;
	}
}
