import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const NAV = [
  { to: "/analytics", label: "Analytics" },
  { to: "/radar", label: "Xu hướng" },
  { to: "/accounts", label: "Tài khoản" },
  { to: "/sources", label: "Media" },
  { to: "/publish", label: "Đăng bài" },
  { to: "/proxies", label: "Proxy" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-gray-200 bg-white p-4 sm:flex">
        <div className="mb-6 px-2 text-lg font-bold">Threads Tool</div>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "bg-black text-white"
                    : "text-gray-700 hover:bg-gray-100"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-4 border-t border-gray-100 pt-4">
          <div className="truncate px-2 text-xs text-gray-500">{user?.email}</div>
          <button
            onClick={handleLogout}
            className="mt-2 w-full rounded-md px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-100"
          >
            Đăng xuất
          </button>
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        {/* Top bar cho mobile */}
        <header className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3 sm:hidden">
          <span className="font-bold">Threads Tool</span>
          <button onClick={handleLogout} className="text-sm text-gray-600">
            Đăng xuất
          </button>
        </header>
        <nav className="flex gap-1 border-b border-gray-200 bg-white px-2 py-2 sm:hidden">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `rounded-md px-3 py-1.5 text-sm ${
                  isActive ? "bg-black text-white" : "text-gray-700"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <main className="flex-1 p-4 sm:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
