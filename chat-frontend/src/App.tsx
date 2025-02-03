import {
	Navigate,
	Route,
	BrowserRouter as Router,
	Routes,
} from "react-router-dom";
import ChatPage from "./pages/ChatPage";
import HomePage from "./pages/HomePage";

function App() {
	return (
		<Router>
			<Routes>
				<Route path="/" element={<Navigate to="/users/1" replace />} />
				<Route path="/users/:userId" element={<HomePage />} />
				<Route path="/users/:userId/chat" element={<ChatPage />} />
			</Routes>
		</Router>
	);
}

export default App;
