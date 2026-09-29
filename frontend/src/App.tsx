import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Competitors from "./pages/Competitors";
import Dashboard from "./pages/Dashboard";
import Export from "./pages/Export";
import History from "./pages/History";
import ProductDetail from "./pages/ProductDetail";
import Products from "./pages/Products";
import Settings from "./pages/Settings";
import Top from "./pages/Top";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/products" element={<Products />} />
        <Route path="/products/:id" element={<ProductDetail />} />
        <Route path="/competitors" element={<Competitors />} />
        <Route path="/top" element={<Top />} />
        <Route path="/history" element={<History />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/export" element={<Export />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
