import React from 'react'
import { Link } from 'react-router-dom'

export default function Sidebar(){
  return (
    <aside style={{width:200}}>
      <nav>
        <Link to="/">Dashboard</Link>
      </nav>
    </aside>
  )
}
