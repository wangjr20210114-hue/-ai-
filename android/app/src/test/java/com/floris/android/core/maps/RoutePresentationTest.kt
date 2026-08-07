package com.floris.android.core.maps

import com.floris.android.core.model.Place
import com.floris.android.core.model.RouteLeg
import com.floris.android.core.model.RoutePlan
import com.floris.android.core.model.RoutePoint
import com.floris.android.core.model.RouteSection
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RoutePresentationTest {
    private val origin = Place(name = "上海虹桥站", city = "上海")
    private val destination = Place(name = "杭州东站", city = "杭州")
    private val path = (0..10).map { index ->
        RoutePoint(latitude = 31.0 - index * 0.02, longitude = 121.0 - index * 0.03)
    }

    @Test
    fun `route without legs gets one provider-backed presentation leg`() {
        val legs = routeLegs(
            RoutePlan(
                mode = "transit",
                places = listOf(origin, destination),
                path = path,
                distance_meters = 190_000.0,
            ),
        )

        assertEquals(1, legs.size)
        assertEquals("intercity", routeLegScope(legs.single()))
        assertEquals(path, legs.single().sections.single().path)
    }

    @Test
    fun `legacy leg path is split by real section weights`() {
        val leg = RouteLeg(
            from = origin,
            to = destination,
            mode = "transit",
            path = path,
            sections = listOf(
                RouteSection(mode = "walking", distance_meters = 1_000.0),
                RouteSection(mode = "rail", distance_meters = 8_000.0),
                RouteSection(mode = "walking", distance_meters = 1_000.0),
            ),
        )
        val steps = routeSectionSteps(RoutePlan(legs = listOf(leg)))

        assertEquals(3, steps.size)
        assertTrue(routeSectionPath(steps[1]).size > routeSectionPath(steps[0]).size)
        assertEquals(path.first(), routeSectionPath(steps.first()).first())
        assertEquals(path.last(), routeSectionPath(steps.last()).last())
    }

    @Test
    fun `section endpoints use provider stops before leg fallback`() {
        val leg = RouteLeg(
            from = origin,
            to = destination,
            sections = listOf(
                RouteSection(mode = "walking", getoff = "虹桥火车站"),
                RouteSection(mode = "rail", geton = "虹桥火车站", getoff = "杭州东"),
                RouteSection(mode = "walking", geton = "杭州东"),
            ),
        )
        val steps = routeSectionSteps(RoutePlan(legs = listOf(leg)))

        assertEquals(
            RouteSectionEndpoints("虹桥火车站", "杭州东"),
            routeSectionEndpoints(steps, 1),
        )
    }

    @Test
    fun `walking display is dotted without changing trusted section path`() {
        val step = RouteSectionStep(
            leg = RouteLeg(path = path),
            legIndex = 0,
            section = RouteSection(
                mode = "walking",
                path = path,
                distance_meters = 2_000.0,
            ),
            sectionIndex = 0,
        )
        val display = routeSectionDisplayPaths(step)

        assertTrue(display.size > 1)
        assertTrue(display.all { it.size == 2 })
        assertEquals(path, step.section.path)
    }
}
