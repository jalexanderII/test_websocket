import type { JsonValue } from "../types/json";

export function renderStructuredData(data: JsonValue): React.ReactNode {
	if (typeof data !== "object" || data === null) {
		return String(data);
	}

	if (Array.isArray(data)) {
		return (
			<div className="space-y-1">
				{data.map((item, index) => (
					<div
						key={`array-item-${index}-${JSON.stringify(item).slice(0, 20)}`}
						className="pl-2"
					>
						{renderStructuredData(item)}
					</div>
				))}
			</div>
		);
	}

	return Object.entries(data).map(([key, value]) => (
		<div key={key} className="space-y-1">
			<div className="font-medium capitalize">{key}:</div>
			<div className="pl-2">{renderStructuredData(value)}</div>
		</div>
	));
}
