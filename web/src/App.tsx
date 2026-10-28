import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import HomePage from "./pages/HomePage";
import ListPage from "./pages/ListPage";
import PlanPage from "./pages/PlanPage";
import ComparePage from "./pages/ComparePage";
import AddPricePage from "./pages/AddPricePage";
import ScanPage from "./pages/ScanPage";
import FlyersPage from "./pages/FlyersPage";
import AccountPage from "./pages/AccountPage";
import LegalPage from "./pages/LegalPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="list" element={<ListPage />} />
        <Route path="plan" element={<PlanPage />} />
        <Route path="compare" element={<ComparePage />} />
        <Route path="add-price" element={<AddPricePage />} />
        <Route path="scan" element={<ScanPage />} />
        <Route path="flyers" element={<FlyersPage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="legal/:doc" element={<LegalPage />} />
        <Route path="*" element={<HomePage />} />
      </Route>
    </Routes>
  );
}
