package com.floris.android.core.maps

import com.floris.android.core.model.RouteLeg
import com.floris.android.core.model.RoutePlan
import com.floris.android.core.model.RoutePoint
import com.floris.android.core.model.RouteSection
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/** Render-only projection of provider-backed route data. No route is computed here. */
data class RouteSectionStep(
    val leg: RouteLeg,
    val legIndex: Int,
    val section: RouteSection,
    val sectionIndex: Int,
)

data class RouteSectionEndpoints(val from: String, val to: String)

fun routeLegs(route: RoutePlan): List<RouteLeg> {
    if (route.legs.isNotEmpty()) return route.legs
    val places = route.places.ifEmpty { route.ordered_stops }
    if (places.size < 2) return emptyList()
    return listOf(
        RouteLeg(
            from = places.first(),
            to = places.last(),
            mode = route.mode,
            path = route.path,
            sections = listOf(
                RouteSection(
                    mode = route.mode ?: "driving",
                    path = route.path,
                    distance_meters = route.distance_meters,
                    duration_seconds = route.duration_seconds,
                ),
            ),
            distance_meters = route.distance_meters,
            duration_seconds = route.duration_seconds,
        ),
    )
}

fun routeLegScope(leg: RouteLeg): String {
    leg.scope?.takeIf(String::isNotBlank)?.let { return it }
    val origin = leg.from?.city.orEmpty().trim().lowercase()
    val destination = leg.to?.city.orEmpty().trim().lowercase()
    return when {
        origin.isEmpty() || destination.isEmpty() -> "unknown"
        origin == destination -> "local"
        else -> "intercity"
    }
}

fun routeSectionSteps(route: RoutePlan): List<RouteSectionStep> =
    routeLegs(route).flatMapIndexed { legIndex, leg ->
        val sections = leg.sections.ifEmpty {
            listOf(
                RouteSection(
                    mode = leg.mode ?: "driving",
                    path = leg.path,
                    distance_meters = leg.distance_meters,
                    duration_seconds = leg.duration_seconds,
                ),
            )
        }
        sections.mapIndexed { sectionIndex, section ->
            RouteSectionStep(leg, legIndex, section, sectionIndex)
        }
    }

fun routeSectionEndpoints(steps: List<RouteSectionStep>, index: Int): RouteSectionEndpoints? {
    val current = steps.getOrNull(index) ?: return null
    val explicitFrom = current.section.geton.orEmpty().trim()
    val explicitTo = current.section.getoff.orEmpty().trim()
    if (explicitFrom.isNotEmpty() && explicitTo.isNotEmpty()) {
        return RouteSectionEndpoints(explicitFrom, explicitTo)
    }
    var from = current.leg.from?.name.orEmpty().trim()
    for (cursor in index - 1 downTo 0) {
        val previous = steps[cursor]
        if (previous.legIndex != current.legIndex) break
        val endpoint = (previous.section.getoff ?: previous.section.geton).orEmpty().trim()
        if (endpoint.isNotEmpty()) {
            from = endpoint
            break
        }
    }
    var to = current.leg.to?.name.orEmpty().trim()
    for (cursor in index + 1 until steps.size) {
        val next = steps[cursor]
        if (next.legIndex != current.legIndex) break
        val endpoint = (next.section.geton ?: next.section.getoff).orEmpty().trim()
        if (endpoint.isNotEmpty()) {
            to = endpoint
            break
        }
    }
    return if (from.isNotEmpty() && to.isNotEmpty() && from != to) {
        RouteSectionEndpoints(from, to)
    } else null
}

/** Split an older leg-only provider path proportionally across its real sections. */
fun routeSectionPath(step: RouteSectionStep): List<RoutePoint> {
    val leg = step.leg
    val section = step.section
    if (section.path.size > 1 || leg.path.size < 2) return section.path
    val sections = leg.sections.ifEmpty { listOf(section) }
    val weights = sections.map {
        when {
            it.distance_meters > 0 -> it.distance_meters
            it.duration_seconds > 0 -> it.duration_seconds
            else -> 1.0
        }
    }
    val total = weights.sum().takeIf { it > 0 } ?: 1.0
    val before = weights.take(step.sectionIndex).sum()
    val after = before + (weights.getOrNull(step.sectionIndex) ?: 1.0)
    val last = leg.path.lastIndex
    val start = ((before / total) * last).toInt().coerceIn(0, last)
    val end = kotlin.math.ceil((after / total) * last).toInt().coerceIn(0, last)
    return leg.path.subList(start, max(start + 2, end + 1).coerceAtMost(leg.path.size))
}

/** Render-only walking geometry: lightly simplify, then split into round-cap dots. */
fun routeSectionDisplayPaths(step: RouteSectionStep): List<List<RoutePoint>> {
    val path = routeSectionPath(step)
    if (step.section.mode != "walking" || path.size < 2) return listOf(path)
    val tolerance = max(6.0, min(18.0, step.section.distance_meters / 120.0))
    return dottedWalkingPaths(simplifyPath(path, tolerance))
}

private fun simplifyPath(path: List<RoutePoint>, toleranceMeters: Double): List<RoutePoint> {
    if (path.size < 3) return path
    val keep = mutableSetOf(0, path.lastIndex)
    val pending = ArrayDeque<Pair<Int, Int>>().apply { add(0 to path.lastIndex) }
    val toleranceSquared = toleranceMeters * toleranceMeters
    while (pending.isNotEmpty()) {
        val (start, end) = pending.removeLast()
        var farthest = -1
        var distance = 0.0
        for (index in start + 1 until end) {
            val candidate = segmentDistanceSquared(path[index], path[start], path[end])
            if (candidate > distance) {
                distance = candidate
                farthest = index
            }
        }
        if (farthest >= 0 && distance > toleranceSquared) {
            keep += farthest
            pending += start to farthest
            pending += farthest to end
        }
    }
    return keep.sorted().map(path::get)
}

private fun dottedWalkingPaths(path: List<RoutePoint>): List<List<RoutePoint>> {
    val totalMeters = path.zipWithNext().sumOf { (start, end) -> sqrt(metersSquared(start, end)) }
    val cycle = max(46.0, totalMeters / 160.0)
    val dash = cycle * 0.61
    val gap = cycle - dash
    var drawing = true
    var remaining = dash
    val result = mutableListOf<List<RoutePoint>>()
    path.zipWithNext().forEach { (start, end) ->
        val distance = sqrt(metersSquared(start, end))
        if (distance <= 0) return@forEach
        var offset = 0.0
        while (offset < distance) {
            val length = min(remaining, distance - offset)
            if (drawing && length > 0.5) {
                result += listOf(interpolate(start, end, offset / distance), interpolate(start, end, (offset + length) / distance))
            }
            offset += length
            remaining -= length
            if (remaining <= 0.5) {
                drawing = !drawing
                remaining = if (drawing) dash else gap
            }
        }
    }
    return result.ifEmpty { listOf(path) }
}

private fun interpolate(start: RoutePoint, end: RoutePoint, ratio: Double) = RoutePoint(
    latitude = start.latitude + (end.latitude - start.latitude) * ratio,
    longitude = start.longitude + (end.longitude - start.longitude) * ratio,
)

private fun metersSquared(a: RoutePoint, b: RoutePoint): Double {
    val latitude = ((a.latitude + b.latitude) / 2) * Math.PI / 180
    val dx = (a.longitude - b.longitude) * 111_320 * cos(latitude)
    val dy = (a.latitude - b.latitude) * 110_540
    return dx * dx + dy * dy
}

private fun segmentDistanceSquared(point: RoutePoint, start: RoutePoint, end: RoutePoint): Double {
    val latitude = point.latitude * Math.PI / 180
    val scaleX = 111_320 * cos(latitude)
    val scaleY = 110_540.0
    val ax = start.longitude * scaleX
    val ay = start.latitude * scaleY
    val bx = end.longitude * scaleX
    val by = end.latitude * scaleY
    val px = point.longitude * scaleX
    val py = point.latitude * scaleY
    val dx = bx - ax
    val dy = by - ay
    val length = dx * dx + dy * dy
    val ratio = if (length > 0) (((px - ax) * dx + (py - ay) * dy) / length).coerceIn(0.0, 1.0) else 0.0
    val ox = px - (ax + ratio * dx)
    val oy = py - (ay + ratio * dy)
    return ox * ox + oy * oy
}
