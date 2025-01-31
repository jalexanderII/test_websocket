import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import HomePage from './pages/HomePage'
import ChatPage from './pages/ChatPage'

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

export default App
