import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'
import {
  BookOpen,
  ChevronDown,
  CircleHelp,
  ClipboardCheck,
  ClipboardList,
  Database,
  Eye,
  FileEdit,
  FileSearch,
  FileText,
  FlaskConical,
  GitCompareArrows,
  Layers,
  LayoutDashboard,
  Mic,
  Rocket,
  Settings,
  Sparkles,
  Sun,
  TestTube2,
  User,
  Wrench,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'
import { toolsGroupLabel } from '../../constants/app'
import { useUser, type UserRole } from '../../context/UserContext'

type NavItem = {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  badge?: string
}

type NavGroup = {
  label: string
  icon: LucideIcon
  items: NavItem[]
}

const buildPmGroup = (displayName: string): NavGroup => ({
  label: toolsGroupLabel(displayName),
  icon: Wrench,
  items: [
    { to: '/pm/standup', label: 'Standup Diario', icon: Sun },
    { to: '/pm/prd-checker', label: 'Revisor de PRD', icon: FileSearch },
    { to: '/pm/change-impact', label: 'Impacto de Cambios', icon: GitCompareArrows },
  ],
})

const FUNCIONAL_GROUP: NavGroup = {
  label: 'Funcional',
  icon: Layers,
  items: [
    { to: '/funcional/transcripciones', label: 'Transcripción de Reuniones', icon: Mic, badge: 'Nuevo' },
    { to: '/funcional/inventario', label: 'Inventario', icon: FileText },
    { to: '/funcional/levantamiento', label: 'Levantamiento', icon: ClipboardList },
    { to: '/funcional/mejoras', label: 'Documento de Mejoras', icon: FileEdit },
  ],
}

const QA_GROUP: NavGroup = {
  label: 'Herramientas QA',
  icon: FlaskConical,
  items: [
    { to: '/qa/regression', label: 'Regresión', icon: TestTube2 },
    { to: '/qa/api-qa', label: 'QA de API', icon: ClipboardCheck },
    { to: '/qa/visual-qa', label: 'QA Visual', icon: Eye },
    { to: '/qa/smart-test-data', label: 'Datos de Prueba Inteligentes', icon: Database },
    { to: '/qa/release-readiness', label: 'Estado de Lanzamiento', icon: Rocket },
  ],
}

const KNOWLEDGE_GROUP: NavGroup = {
  label: 'Conocimiento',
  icon: BookOpen,
  items: [
    { to: '/knowledge', label: 'Biblioteca', icon: BookOpen, end: true },
    { to: '/knowledge/ask', label: 'Consultar Producto', icon: CircleHelp },
  ],
}

type TopNavProps = {
  displayName: string
}

const navLinkClass = (isActive: boolean) =>
  [
    'flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium whitespace-nowrap transition-all duration-200',
    isActive
      ? 'bg-blue-50 text-[#002777] shadow-sm ring-1 ring-blue-200'
      : 'text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-ink)] hover:shadow-sm',
  ].join(' ')

type MenuPosition = {
  top: number
  left: number
}

const NavDropdown = ({ group }: { group: NavGroup }) => {
  const [open, setOpen] = useState(false)
  const [menuPos, setMenuPos] = useState<MenuPosition | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const location = useLocation()
  const GroupIcon = group.icon
  const isChildActive = group.items.some((item) =>
    item.end ? location.pathname === item.to : location.pathname.startsWith(item.to),
  )

  const updateMenuPosition = () => {
    if (!buttonRef.current) return
    const rect = buttonRef.current.getBoundingClientRect()
    setMenuPos({ top: rect.bottom + 6, left: rect.left })
  }

  useEffect(() => {
    if (!open) return

    updateMenuPosition()

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      if (buttonRef.current?.contains(target)) return
      const menu = document.getElementById(`nav-menu-${group.label}`)
      if (menu?.contains(target)) return
      setOpen(false)
    }

    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    const handleScroll = () => updateMenuPosition()

    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)
    window.addEventListener('resize', handleScroll)
    window.addEventListener('scroll', handleScroll, true)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
      window.removeEventListener('resize', handleScroll)
      window.removeEventListener('scroll', handleScroll, true)
    }
  }, [open, group.label])

  const handleToggle = () => {
    if (!open) updateMenuPosition()
    setOpen((prev) => !prev)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      handleToggle()
    }
  }

  const menu = open && menuPos
    ? createPortal(
      <div
        id={`nav-menu-${group.label}`}
        className="min-w-[220px] rounded-xl border border-[var(--color-border)] bg-white py-1.5 shadow-xl shadow-blue-900/10"
        style={{ position: 'fixed', top: menuPos.top, left: menuPos.left, zIndex: 9999 }}
        role="menu"
      >
        {group.items.map((item) => {
          const ItemIcon = item.icon
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              role="menuitem"
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                [
                  'mx-1.5 flex items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors',
                  isActive
                    ? 'bg-blue-50 font-medium text-[#002777]'
                    : 'text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-ink)]',
                ].join(' ')
              }
            >
              <div className="flex items-center gap-2.5">
                <ItemIcon className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800">
                  {item.badge}
                </span>
              )}
            </NavLink>
          )
        })}
      </div>,
      document.body,
    )
    : null

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className={[
          'flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-medium whitespace-nowrap transition-all duration-200',
          open || isChildActive
            ? 'bg-blue-50 text-[#002777] shadow-sm ring-1 ring-blue-200'
            : 'text-[var(--color-ink-muted)] hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-ink)] hover:shadow-sm',
        ].join(' ')}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={`${group.label} menu`}
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
      >
        <GroupIcon className="h-4 w-4 shrink-0 opacity-70" aria-hidden />
        <span>{group.label}</span>
        <ChevronDown
          className={['h-4 w-4 shrink-0 opacity-50 transition-transform duration-200', open ? 'rotate-180' : ''].join(' ')}
          aria-hidden
        />
      </button>
      {menu}
    </>
  )
}

const roleLabels: Record<UserRole, string> = {
  admin: 'Administrador',
  pm: 'Project Manager',
  funcional: 'Analista Funcional',
  qa: 'Tester',
}

const UserDropdown = ({ displayName }: { displayName: string }) => {
  const [open, setOpen] = useState(false)
  const [menuPos, setMenuPos] = useState<MenuPosition | null>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  const updateMenuPosition = () => {
    if (!buttonRef.current) return
    const rect = buttonRef.current.getBoundingClientRect()
    const menuWidth = 256 // w-64 is 16rem = 256px
    const margin = 16
    const left = Math.min(
      Math.max(margin, rect.right - menuWidth),
      window.innerWidth - menuWidth - margin,
    )
    setMenuPos({ top: rect.bottom + 8, left })
  }

  useEffect(() => {
    if (!open) return

    updateMenuPosition()

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      if (buttonRef.current?.contains(target)) return
      const menu = document.getElementById('user-avatar-dropdown-menu')
      if (menu?.contains(target)) return
      setOpen(false)
    }

    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }

    const handleScroll = () => updateMenuPosition()

    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)
    window.addEventListener('resize', handleScroll)
    window.addEventListener('scroll', handleScroll, true)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
      window.removeEventListener('resize', handleScroll)
      window.removeEventListener('scroll', handleScroll, true)
    }
  }, [open])

  const { user } = useUser()
  const activeName = user?.display_name || displayName
  const roleLabel = roleLabels[user?.user_role || 'admin']

  const getInitials = (nameStr: string) => {
    const parts = nameStr.trim().split(/\s+/).filter(Boolean)
    if (parts.length === 0) return 'U'
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase()
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
  }

  const initials = getInitials(activeName)

  const handleToggle = () => {
    if (!open) updateMenuPosition()
    setOpen((prev) => !prev)
  }

  const menu = open && menuPos
    ? createPortal(
      <div
        id="user-avatar-dropdown-menu"
        className="w-64 rounded-2xl border border-[var(--color-border)] bg-white p-2.5 shadow-xl shadow-slate-900/10 text-[var(--color-ink)]"
        style={{ position: 'fixed', top: menuPos.top, left: menuPos.left, zIndex: 9999 }}
        role="menu"
      >
        {/* Profile Card */}
        <div className="flex items-center gap-3.5 p-2 rounded-xl">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#002777] to-[#004497] text-white font-extrabold text-sm shadow-md shadow-[#002777]/20">
            {initials}
          </div>
          <div className="min-w-0 flex-1 overflow-hidden">
            <p
              className="text-sm font-bold text-slate-900 truncate max-w-[175px] leading-snug"
              title={activeName}
            >
              {activeName}
            </p>
            <p
              className="text-xs text-blue-700 font-semibold truncate max-w-[175px] mt-0.5"
              title={roleLabel}
            >
              {roleLabel}
            </p>
          </div>
        </div>

        <div className="border-t border-slate-100 my-1.5" />

        {/* Menu Options */}
        <div className="space-y-0.5">
          <NavLink
            to="/profile"
            role="menuitem"
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors cursor-pointer',
                isActive
                  ? 'bg-blue-50 text-[#002777] font-semibold'
                  : 'text-slate-700 hover:bg-slate-100/80 hover:text-slate-900',
              ].join(' ')
            }
          >
            <User className="h-4 w-4 shrink-0 text-slate-500" />
            <span>Perfil</span>
          </NavLink>

          <NavLink
            to="/settings"
            role="menuitem"
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors cursor-pointer',
                isActive
                  ? 'bg-blue-50 text-[#002777] font-semibold'
                  : 'text-slate-700 hover:bg-slate-100/80 hover:text-slate-900',
              ].join(' ')
            }
          >
            <Settings className="h-4 w-4 shrink-0 text-slate-500" />
            <span>Configuración</span>
          </NavLink>
        </div>
      </div>,
      document.body,
    )
    : null

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={handleToggle}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-[#002777] to-[#004497] text-white text-xs font-extrabold shadow-md shadow-[#002777]/20 ring-2 ring-blue-100 transition-transform hover:scale-105 hover:ring-blue-300 focus:outline-none focus:ring-2 focus:ring-[#002777] cursor-pointer"
        title={`${activeName} (${roleLabel}) - Menú de opciones`}
        aria-label={`Menú de usuario para ${activeName}`}
        aria-haspopup="true"
        aria-expanded={open}
      >
        {initials}
      </button>

      {menu}
    </>
  )
}

export const TopNav = ({ displayName }: TopNavProps) => {
  const { user } = useUser()
  const role: UserRole = user?.user_role || 'admin'
  const activeDisplayName = user?.display_name || displayName

  const PM_GROUP = buildPmGroup(activeDisplayName)

  const showPm = ['admin', 'pm'].includes(role)
  const showFuncional = ['admin', 'funcional'].includes(role)
  const showQa = ['admin', 'qa'].includes(role)
  const showKnowledge = ['admin', 'pm', 'qa', 'funcional'].includes(role)

  return (
    <header className="sticky top-0 z-40 overflow-visible border-b border-[var(--color-border)] bg-white/90 backdrop-blur-xl">
      <div
        className="h-0.5 w-full bg-gradient-to-r from-[#002777] via-[#004497] to-cyan-400"
        aria-hidden
      />

      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 md:gap-x-6 md:px-6">
        <NavLink
          to="/"
          className="group flex shrink-0 items-center gap-2.5"
          aria-label="QA Project MGMT home"
        >
          <div className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#002777] to-[#004497] text-white shadow-lg shadow-[#002777]/30 transition-transform duration-300 group-hover:scale-105">
            <Sparkles className="h-4 w-4" aria-hidden />
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-cyan-400 ring-2 ring-white animate-pulse-soft" aria-hidden />
          </div>
          <span className="text-sm font-bold tracking-tight text-[var(--color-ink)]">
            QA Project <span className="font-normal text-[var(--color-primary-accent)]">MGMT</span>
          </span>
        </NavLink>

        <nav className="flex flex-1 flex-wrap items-center gap-0.5" aria-label="Primary navigation">
          <NavLink to="/" end className={({ isActive }) => navLinkClass(isActive)}>
            <LayoutDashboard className="h-4 w-4 shrink-0" aria-hidden />
            <span>Inicio</span>
          </NavLink>

          {showPm && <NavDropdown group={PM_GROUP} />}
          {showFuncional && <NavDropdown group={FUNCIONAL_GROUP} />}
          {showQa && <NavDropdown group={QA_GROUP} />}
          {showKnowledge && <NavDropdown group={KNOWLEDGE_GROUP} />}
        </nav>

        <div className="flex shrink-0 items-center gap-2.5">
          <UserDropdown displayName={activeDisplayName} />
        </div>
      </div>
    </header>
  )
}
