package com.floris.android.ui.maps

import android.annotation.SuppressLint
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.floris.android.AppContainer
import com.floris.android.R
import com.floris.android.ui.components.CatIconPill
import com.floris.android.BuildConfig
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.model.Place
import com.floris.android.core.model.RoutePlan
import com.floris.android.core.model.SkillAccess
import com.floris.android.core.model.SkillAccessStatus
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.SkillAccessNotice
import com.floris.android.ui.components.routeModeLabel
import com.floris.android.ui.mapViewModelFactory
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.StringResolver
import com.floris.android.ui.prefs.t
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MapViewModel(
    private val repository: FlorisRepository,
    private val strings: StringResolver,
) : ViewModel() {

    data class UiState(
        val searching: Boolean = false,
        val searchResults: List<Place> = emptyList(),
        val planningRoute: Boolean = false,
        val route: RoutePlan? = null,
        val routeMode: String = "driving",
        val error: String? = null,
        val access: SkillAccess = SkillAccess(MAPS_SKILL_ID, SkillAccessStatus.Loading),
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    /** Backend-confirmed map workspace (from chat map actions). */
    val workspace = repository.mapWorkspaceFlow

    init {
        viewModelScope.launch {
            repository.skillAccessFlow.collect { projection ->
                val access = projection.access(MAPS_SKILL_ID)
                _state.value = _state.value.copy(
                    access = access,
                    searching = if (access.available) _state.value.searching else false,
                    planningRoute = if (access.available) _state.value.planningRoute else false,
                )
            }
        }
        viewModelScope.launch {
            runCatching { repository.ensureSkillAccess(repository.activeConversationId()) }
        }
    }

    fun searchPlaces(query: String) {
        if (query.isBlank() || !_state.value.access.available) return
        _state.value = _state.value.copy(searching = true, error = null)
        viewModelScope.launch {
            runCatching {
                repository.searchPlaces(repository.activeConversationId(), query)
            }.onSuccess { places ->
                _state.value = _state.value.copy(searching = false, searchResults = places)
            }.onFailure {
                _state.value = _state.value.copy(
                    searching = false,
                    error = strings.get(StringKey.MapSearchFailed),
                )
            }
        }
    }

    fun planRoute(places: List<Place>, mode: String) {
        if (!_state.value.access.available) return
        if (places.size < 2) {
            _state.value = _state.value.copy(error = strings.get(StringKey.MapNeedTwoPlaces))
            return
        }
        _state.value = _state.value.copy(planningRoute = true, routeMode = mode, error = null)
        viewModelScope.launch {
            runCatching {
                repository.planRoute(repository.activeConversationId(), places, mode = mode)
            }.onSuccess { route ->
                _state.value = _state.value.copy(
                    planningRoute = false,
                    route = route,
                    error = if (route == null) strings.get(StringKey.MapServiceUnavailable) else null,
                )
            }.onFailure {
                _state.value = _state.value.copy(
                    planningRoute = false,
                    error = strings.get(StringKey.MapPlanFailed),
                )
            }
        }
    }

    fun clearRoute() { _state.value = _state.value.copy(route = null) }
    fun consumeError() { _state.value = _state.value.copy(error = null) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen(
    container: AppContainer,
    onBack: () -> Unit,
    onRequestLogin: () -> Unit = {},
    onOpenSkills: () -> Unit = {},
) {
    val viewModel: MapViewModel = viewModel(factory = container.mapViewModelFactory())
    val state by viewModel.state.collectAsState()
    val workspace by viewModel.workspace.collectAsState()

    if (!state.access.available) {
        Column(
            Modifier
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
                .statusBarsPadding()
                .navigationBarsPadding(),
        ) {
            Row(
                Modifier.fillMaxWidth().padding(start = 8.dp, end = 16.dp, top = 4.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                CatIconPill(
                    resId = R.drawable.ic_back,
                    contentDescription = t(StringKey.Back),
                    onClick = onBack,
                )
                Spacer(Modifier.width(4.dp))
                Text(t(StringKey.MapTitle), style = MaterialTheme.typography.headlineMedium)
            }
            // 能力未开启时也先展示地图组件本身，给用户完整的前端体验。
            if (BuildConfig.TENCENT_MAP_KEY.isNotEmpty()) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 10.dp)
                        .height(260.dp)
                        .clip(RoundedCornerShape(18.dp)),
                ) {
                    TencentMapView(
                        places = workspace.places,
                        route = null,
                        modifier = Modifier.fillMaxSize(),
                    )
                }
            }
            Box(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                SkillAccessNotice(state.access, onRequestLogin, onOpenSkills)
            }
        }
        return
    }
    var query by remember { mutableStateOf("") }
    val snackbar = androidx.compose.material3.SnackbarHostState()
    androidx.compose.runtime.LaunchedEffect(state.error) {
        state.error?.let { snackbar.showSnackbar(it); viewModel.consumeError() }
    }

    val displayPlaces = state.searchResults.ifEmpty { workspace.places }
    val displayRoute = state.route ?: workspace.route

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding()
            .navigationBarsPadding(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = 8.dp, end = 16.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CatIconPill(
                resId = R.drawable.ic_back,
                contentDescription = t(StringKey.Back),
                onClick = onBack,
            )
            Spacer(Modifier.width(4.dp))
            Text(
                workspace.title ?: t(StringKey.MapTitle),
                style = MaterialTheme.typography.headlineMedium,
                maxLines = 1,
                overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
            )
        }

        Box(Modifier.weight(1f)) {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                item(key = "search") {
                    com.floris.android.ui.papers.SearchField(
                        value = query,
                        onValueChange = { query = it },
                        hint = t(StringKey.MapSearchHint),
                        onSearch = { viewModel.searchPlaces(query) },
                    )
                }

            if (BuildConfig.TENCENT_MAP_KEY.isNotEmpty() && displayPlaces.isNotEmpty()) {
                item(key = "map") {
                    TencentMapView(
                        places = displayPlaces,
                        route = displayRoute,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(260.dp)
                            .clip(RoundedCornerShape(18.dp)),
                    )
                }
            }

            if (state.searching) item(key = "loading") { InlineLoading() }

            if (displayPlaces.isNotEmpty()) {
                item(key = "places-header") {
                    Row(
                        Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        SectionHeader(t(StringKey.MapPlaces, displayPlaces.size), Modifier.weight(1f))
                        workspace.routeMode?.let {
                            StatusChip(routeModeLabel(it), MaterialTheme.colorScheme.primary)
                        }
                    }
                }
                items(displayPlaces, key = { it.place_id.ifEmpty { it.name } }) { place ->
                    FlorisCard {
                        Row(
                            Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                Icons.Default.LocationOn, null,
                                tint = MaterialTheme.colorScheme.primary,
                                modifier = Modifier.size(18.dp),
                            )
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(place.name, style = MaterialTheme.typography.titleMedium)
                                Text(
                                    listOfNotNull(place.city, place.address.ifEmpty { null })
                                        .joinToString(" · "),
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    maxLines = 1,
                                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                                )
                            }
                        }
                    }
                }

                if (displayPlaces.size >= 2) {
                    item(key = "route-modes") {
                        Column {
                            SectionHeader(t(StringKey.MapRoute))
                            com.floris.android.ui.components.SegmentedControl(
                                options = listOf("driving", "transit", "walking", "bicycling")
                                    .map { routeModeLabel(it) },
                                selectedIndex = listOf("driving", "transit", "walking", "bicycling")
                                    .indexOf(state.routeMode).coerceAtLeast(0),
                                onSelect = { index ->
                                    if (!state.planningRoute) {
                                        viewModel.planRoute(
                                            displayPlaces,
                                            listOf("driving", "transit", "walking", "bicycling")[index],
                                        )
                                    }
                                },
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }
                    }
                }

                displayRoute?.let { route ->
                    item(key = "route") {
                        RouteCard(route, state.planningRoute)
                    }
                }
                } else if (!state.searching) {
                    item(key = "empty") {
                        EmptyState(t(StringKey.MapEmptyTitle), t(StringKey.MapEmptyBody))
                    }
                }
            }
            androidx.compose.material3.SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter))
        }
    }
}

@Composable
private fun RouteCard(route: RoutePlan, planning: Boolean) {
    FlorisCard {
        Column(Modifier.padding(14.dp)) {
            val places = route.places.ifEmpty { route.ordered_stops }
            val distance = route.distance_text ?: route.distance_meters.takeIf { it > 0 }?.let(::distanceText)
            val duration = route.duration_text
                ?: route.duration_seconds.takeIf { it > 0 }?.let { durationText(it) }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(
                        places.takeIf { it.size >= 2 }?.let {
                            "${it.first().name} → ${it.last().name}"
                        } ?: t(StringKey.MapNamedRoute, routeModeLabel(route.mode ?: "")),
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                    )
                    Text(
                        listOfNotNull(distance, duration, route.cost_text).joinToString(" · "),
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                StatusChip(routeModeLabel(route.mode ?: ""), MaterialTheme.colorScheme.primary)
            }
            route.legs.forEachIndexed { index, leg ->
                Spacer(Modifier.height(if (index == 0) 12.dp else 8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        Modifier.size(22.dp).clip(CircleShape)
                            .background(MaterialTheme.colorScheme.primaryContainer),
                        contentAlignment = Alignment.Center,
                    ) {
                        Text("${index + 1}", style = MaterialTheme.typography.labelSmall)
                    }
                    Spacer(Modifier.width(8.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            listOfNotNull(leg.from?.name, leg.to?.name).joinToString(" → ")
                                .ifBlank { leg.instruction.orEmpty() },
                            style = MaterialTheme.typography.labelLarge,
                            maxLines = 1,
                            overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                        )
                        Text(
                            listOfNotNull(
                                leg.distance_text ?: leg.distance_meters.takeIf { it > 0 }?.let(::distanceText),
                                leg.duration_text
                                    ?: leg.duration_seconds.takeIf { it > 0 }?.let { durationText(it) },
                            ).joinToString(" · "),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                val sections = leg.sections
                Row(
                    Modifier.padding(start = 30.dp, top = 7.dp)
                        .horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (sections.isEmpty()) {
                        leg.mode?.let { mode ->
                            StatusChip(routeModeLabel(mode), routeModeColor(mode))
                        }
                    } else sections.forEachIndexed { sectionIndex, section ->
                        StatusChip(
                            section.line?.takeIf { it.isNotBlank() }
                                ?: section.vehicle?.takeIf { it.isNotBlank() }
                                ?: routeModeLabel(section.mode),
                            routeModeColor(section.mode),
                        )
                        if (sectionIndex < sections.lastIndex) {
                            Icon(
                                Icons.AutoMirrored.Filled.ArrowForward,
                                contentDescription = null,
                                modifier = Modifier.size(13.dp),
                                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

private const val MAPS_SKILL_ID = "maps"

@Composable
private fun routeModeColor(mode: String): Color = when (mode) {
    "rail", "train" -> MaterialTheme.colorScheme.secondary
    "bus", "transit", "subway", "metro" -> MaterialTheme.colorScheme.tertiary
    "bicycling" -> Color(0xFF2F8B68)
    "walking" -> MaterialTheme.colorScheme.onSurfaceVariant
    else -> MaterialTheme.colorScheme.primary
}

private fun distanceText(meters: Double): String =
    if (meters >= 1000) "%.1f km".format(meters / 1000) else "${meters.toInt()} m"

@Composable
private fun durationText(seconds: Double): String {
    val minutes = (seconds / 60).toInt().coerceAtLeast(1)
    return if (minutes >= 60) {
        t(StringKey.DurationHoursMinutes, minutes / 60, minutes % 60)
    } else t(StringKey.DurationMinutes, minutes)
}

/** Tencent GL JS map inside a locked-down WebView; requires TENCENT_MAP_KEY in local.properties. */
@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun TencentMapView(places: List<Place>, route: RoutePlan?, modifier: Modifier = Modifier) {
    val key = BuildConfig.TENCENT_MAP_KEY
    val html = remember(places, route) { buildMapHtml(key, places, route) }
    AndroidView(
        modifier = modifier.background(MaterialTheme.colorScheme.surfaceVariant),
        factory = { context ->
            WebView(context).apply {
                // JavaScript is required by Tencent GL JS. Local files, content providers and
                // mixed content remain disabled; the document has a fixed HTTPS base origin.
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.allowFileAccess = false
                settings.allowContentAccess = false
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
                settings.safeBrowsingEnabled = true
                webViewClient = WebViewClient()
            }
        },
        update = { webView ->
            webView.loadDataWithBaseURL("https://map.qq.com", html, "text/html", "utf-8", null)
        },
    )
}

private fun buildMapHtml(key: String, places: List<Place>, route: RoutePlan?): String {
    val markers = places.joinToString(",") { "{lat:${it.latitude},lng:${it.longitude},name:\"${it.name.jsEscape()}\"}" }
    fun points(points: List<com.floris.android.core.model.RoutePoint>) =
        points.joinToString(",") { "[${it.latitude},${it.longitude}]" }
    val contractPath = route?.path.orEmpty()
    val legacyPath = route?.polyline.orEmpty().map {
        com.floris.android.core.model.RoutePoint(
            it.getOrElse(0) { 0.0 },
            it.getOrElse(1) { 0.0 },
        )
    }
    val coarse = points(contractPath.ifEmpty { legacyPath })
    val legs = route?.legs.orEmpty().mapIndexed { index, leg ->
        val path = leg.path.ifEmpty {
            leg.polyline.map { pair ->
                com.floris.android.core.model.RoutePoint(
                    pair.getOrElse(0) { 0.0 }, pair.getOrElse(1) { 0.0 },
                )
            }
        }
        "{id:'leg$index',scope:'${(leg.scope ?: "unknown").jsEscape()}',mode:'${(leg.mode ?: "driving").jsEscape()}',points:[${points(path)}]}"
    }.orEmpty().joinToString(",")
    val sections = route?.legs.orEmpty().flatMapIndexed { legIndex, leg ->
        leg.sections.mapIndexed { sectionIndex, section ->
            "{id:'section${legIndex}_$sectionIndex',scope:'${(leg.scope ?: "unknown").jsEscape()}',mode:'${section.mode.jsEscape()}',points:[${points(section.path)}]}"
        }
    }.orEmpty().joinToString(",")
    val center = places.firstOrNull() ?: Place(latitude = 39.9, longitude = 116.4)
    return """
        <!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>html,body,#map{margin:0;height:100%}</style>
        <script src="https://map.qq.com/api/gljs?v=1.exp&key=$key"></script></head>
        <body><div id="map"></div><script>
        var map = new TMap.Map(document.getElementById('map'), {
          center: new TMap.LatLng(${center.latitude}, ${center.longitude}), zoom: 12
        });
        var data = [$markers];
        var geometries = data.map(function(p, i) {
          return { id: 'p' + i, position: new TMap.LatLng(p.lat, p.lng), content: p.name };
        });
        new TMap.MultiMarker({ map: map, geometries: geometries });
        var coarse = [$coarse];
        var legs = [$legs];
        var sections = [$sections];
        var styles = {
          driving:{color:'#5B72E8',width:7,borderWidth:1,borderColor:'#FFFFFF'},
          transit:{color:'#2E9C76',width:7,borderWidth:1,borderColor:'#FFFFFF'},
          bus:{color:'#2E9C76',width:7,borderWidth:1,borderColor:'#FFFFFF'},
          rail:{color:'#9A63D4',width:8,borderWidth:1,borderColor:'#FFFFFF'},
          walking:{color:'#8A8178',width:5,dashArray:[5,5]},
          bicycling:{color:'#E98B45',width:6,borderWidth:1,borderColor:'#FFFFFF'}
        };
        var routeLayer = new TMap.MultiPolyline({map:map,styles:styles,geometries:[]});
        function distanceToCenter(item) {
          if (!item.points.length) return 999999;
          var center = map.getCenter(), point = item.points[Math.floor(item.points.length/2)];
          var dx = point[0] - center.lat, dy = point[1] - center.lng;
          return dx*dx + dy*dy;
        }
        function geometry(item) {
          return {id:item.id,styleId:styles[item.mode] ? item.mode : 'driving',
            paths:item.points.map(function(p){return new TMap.LatLng(p[0],p[1]);})};
        }
        function renderRoute() {
          var zoom = map.getZoom(), visible = [];
          if (zoom <= 7) {
            visible = legs.filter(function(item){return item.scope === 'intercity';});
            if (!visible.length && coarse.length > 1) visible = [{id:'route',mode:'driving',points:coarse}];
          } else if (zoom <= 12) {
            visible = legs.length ? legs : [{id:'route',mode:'driving',points:coarse}];
          } else {
            visible = (sections.length ? sections : legs).slice().sort(function(a,b){
              return distanceToCenter(a)-distanceToCenter(b);
            }).slice(0,4);
          }
          routeLayer.setGeometries(visible.filter(function(item){return item.points.length>1;}).map(geometry));
        }
        renderRoute();
        map.on('zoom_changed', renderRoute);
        map.on('center_changed', function(){ if(map.getZoom()>12) renderRoute(); });
        </script></body></html>
    """.trimIndent()
}

private fun String.jsEscape(): String = this
    .replace("\\", "\\\\")
    .replace("'", "\\'")
    .replace("\"", "\\\"")
    .replace("<", "\\u003C")
    .replace(">", "\\u003E")
    .replace("\r", "\\r")
    .replace("\n", "\\n")
