import { cn } from '@/lib/utils'

export function SidebarTOC({ sections, activeSection }) {
  const handleClick = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <nav className="sticky top-20 w-[180px] shrink-0 border-r border-[#d9cebb] pr-3 hidden lg:block">
      <p className="text-[10px] uppercase tracking-[1.5px] text-[#8a7e6d] mb-3">
        On this page
      </p>
      <ul className="space-y-0.5">
        {sections.map((section) => {
          const isActive = activeSection === section.id
          return (
            <li key={section.id}>
              <button
                type="button"
                onClick={() => handleClick(section.id)}
                className={cn(
                  'w-full text-left text-xs px-2.5 py-1.5 rounded cursor-pointer transition-all duration-150',
                  'border-l-2',
                  isActive
                    ? 'text-[#1a6b5a] bg-[#1a6b5a]/[0.08] border-l-[#1a6b5a] font-semibold'
                    : 'text-[#8a7e6d] bg-transparent border-l-transparent hover:text-[#2c2418] hover:bg-[#ede7db]/50'
                )}
              >
                {section.label}
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
