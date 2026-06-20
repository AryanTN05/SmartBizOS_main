import React from 'react';
import { Route, Routes } from 'react-router-dom';

import ReportsList from './pages/ReportsList.jsx';
import ReportDetail from './pages/ReportDetail.jsx';
import ReportCompare from './pages/ReportCompare.jsx';

// Sub-router for the M6 Reports module. Mounted by the admin shell under
// `/admin/reports/*`. The human wires this by replacing the ModuleStub
// route in src/App.jsx with:
//
//   import ReportsRoutes from './modules/reports/routes.jsx';
//   <Route path="reports/*" element={<ReportsRoutes />} />
//
// Note: /compare is listed before /:id so it wins the match.
export default function ReportsRoutes() {
  return (
    <Routes>
      <Route index element={<ReportsList />} />
      <Route path="compare" element={<ReportCompare />} />
      <Route path=":id" element={<ReportDetail />} />
    </Routes>
  );
}
