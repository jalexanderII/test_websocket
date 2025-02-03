import {
	Navigate,
	Route,
	BrowserRouter as Router,
	Routes,
} from "react-router-dom";
import ChatPageV2 from "./pages/ChatPageV2";
import HomePageV2 from "./pages/HomePageV2";

function App() {
	return (
		<Router>
			<Routes>
				<Route path="/" element={<Navigate to="/users/1" replace />} />
				<Route path="/users/:userId" element={<HomePageV2 />} />
				<Route path="/users/:userId/chat" element={<ChatPageV2 />} />
			</Routes>
		</Router>
	);
}

export default App;
