package com.floris.android.ui.maps

import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
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
import com.floris.android.BuildConfig
import com.floris.android.core.data.FlorisRepository
import com.floris.android.core.model.Place
import com.floris.android.core.model.RoutePlan
import com.floris.android.ui.components.EmptyState
import com.floris.android.ui.components.FlorisCard
import com.floris.android.ui.components.InlineLoading
import com.floris.android.ui.components.SectionHeader
import com.floris.android.ui.components.StatusChip
import com.floris.android.ui.components.routeModeLabel
import com.floris.android.ui.mapViewModelFactory
import com.floris.android.ui.prefs.StringKey
import com.floris.android.ui.prefs.t
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MapViewModel(private val repository: FlorisRepository) : ViewModel() {

    data class UiState(
        val searching: Boolean = false,
        val searchResults: List<Place> = emptyList(),
        val planningRoute: Boolean = false,
        val route: RoutePlan? = null,
        val routeMode: String = "driving",
        val error: String? = null,
    )

    private val _state = MutableStateFlow(UiState())
    val state = _state.asStateFlow()

    /** Backend-confirmed map workspace (from chat map actions). */
    val workspace = repository.mapWorkspaceFlow

    fun searchPlaces(query: String) {
        if (query.isBlank()) return
        _state.value = _state.value.copy(searching = true, error = null)
        viewModelScope.launch {
            runCatching {
                repository.searchPlaces(repository.activeConversationId(), query)
            }.onSuccess { places ->
                _state.value = _state.value.copy(searching = false, searchResults = places)
            }.onFailure {
                _state.value = _state.value.copy(searching = false, error = "地点搜索失败")
            }
        }
    }

    fun planRoute(places: List<Place>, mode: String) {
        if (places.size < 2) {
            _state.value = _state.value.copy(error = "至少需要两个地点来规划路线")
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
                    error = if (route == null) "路线服务暂不可用" else null,
                )
            }.onFailure {
                _state.value = _state.value.copy(planningRoute = false, error = "路线规划失败")
            }
        }
    }

    fun clearRoute() { _state.value = _state.value.copy(route = null) }
    fun consumeError() { _state.value = _state.value.copy(error = null) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen(container: AppContainer, onBack: () -> Unit) {
    val viewModel: MapViewModel = viewModel(factory = container.mapViewModelFactory())
    val state by viewModel.state.collectAsState()
    val workspace by viewModel.workspace.collectAsState()
    var query by remember { mutableStateOf("") }
    val snackbar = androidx.compose.material3.SnackbarHostState()
    androidx.compose.runtime.LaunchedEffect(state.error) {
        state.error?.let { snackbar.showSnackbar(it); viewModel.consumeError() }
    }

    val displayPlaces = state.searchResults.ifEmpty { workspace.places }

    Column(
        Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .statusBarsPadding(),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(start = 8.dp, end = 16.dp, top = 4.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            com.floris.android.ui.components.IconPill(
                icon = Icons.AutoMirrored.Filled.ArrowBack,
                contentDescription = "返回",
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
                        route = state.route,
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

                state.route?.let { route ->
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
            Text(
                "${routeModeLabel(route.mode ?: "")}路线",
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                route.distance_text?.let { StatusChip(it, MaterialTheme.colorScheme.primary) }
                route.duration_text?.let { StatusChip(it, MaterialTheme.colorScheme.secondary) }
                route.cost_text?.let { StatusChip(it, MaterialTheme.colorScheme.tertiary) }
            }
            if (route.ordered_stops.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                route.ordered_stops.forEachIndexed { index, stop ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            Modifier.size(20.dp).clip(CircleShape)
                                .background(MaterialTheme.colorScheme.primaryContainer),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                "${index + 1}",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                            )
                        }
                        Spacer(Modifier.width(8.dp))
                        Text(stop.name, style = MaterialTheme.typography.labelLarge)
                    }
                }
            }
            route.legs.forEach { leg ->
                leg.instruction?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }
        }
    }
}

/** Tencent GL JS map inside a WebView; requires TENCENT_MAP_KEY in local.properties. */
@Composable
private fun TencentMapView(places: List<Place>, route: RoutePlan?, modifier: Modifier = Modifier) {
    val key = BuildConfig.TENCENT_MAP_KEY
    val html = remember(places, route) { buildMapHtml(key, places, route) }
    AndroidView(
        modifier = modifier.background(MaterialTheme.colorScheme.surfaceVariant),
        factory = { context ->
            WebView(context).apply {
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
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
    val polyline = route?.polyline.orEmpty().joinToString(",") { pair ->
        "[${pair.getOrElse(0) { 0.0 }},${pair.getOrElse(1) { 0.0 }}]"
    }
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
        var line = [$polyline];
        if (line.length > 1) {
          new TMap.MultiPolyline({ map: map, geometries: [{
            id: 'route', paths: line.map(function(p){ return new TMap.LatLng(p[0], p[1]); })
          }]});
        }
        </script></body></html>
    """.trimIndent()
}

private fun String.jsEscape(): String = replace("\\", "\\\\").replace("\"", "\\\"")
