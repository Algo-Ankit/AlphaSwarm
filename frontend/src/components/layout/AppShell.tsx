import { Sidebar } from './Sidebar'
import { TopBar } from './TopBar'

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Sidebar />
      <TopBar />
      {/*
        contain: layout style — tells the browser the main region is independent
        from fixed sidebar/topbar, eliminating scroll-linked layout recalculation.
      */}
      <main
        className="ml-[240px] pt-[62px] min-h-screen relative z-10"
        style={{ contain: 'layout style' }}
      >
        <div className="max-w-5xl mx-auto p-6 lg:p-10">
          {children}
        </div>
      </main>
    </>
  )
}
