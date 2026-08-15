package com.hyperscale.command.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.outlined.Air
import androidx.compose.material.icons.outlined.BatteryChargingFull
import androidx.compose.material.icons.outlined.Blinds
import androidx.compose.material.icons.outlined.CleaningServices
import androidx.compose.material.icons.outlined.Computer
import androidx.compose.material.icons.outlined.DeviceHub
import androidx.compose.material.icons.outlined.DevicesOther
import androidx.compose.material.icons.outlined.DirectionsCar
import androidx.compose.material.icons.outlined.Doorbell
import androidx.compose.material.icons.outlined.Kitchen
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.PlayCircle
import androidx.compose.material.icons.outlined.Power
import androidx.compose.material.icons.outlined.Print
import androidx.compose.material.icons.outlined.Router
import androidx.compose.material.icons.outlined.Sensors
import androidx.compose.material.icons.outlined.Speaker
import androidx.compose.material.icons.outlined.Thermostat
import androidx.compose.material.icons.outlined.ToggleOn
import androidx.compose.material.icons.outlined.Tv
import androidx.compose.material.icons.outlined.Videocam
import androidx.compose.material.icons.outlined.Watch
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hyperscale.command.core.model.DeviceClass
import com.hyperscale.command.core.model.DeviceStatus
import com.hyperscale.command.core.model.Protocol
import com.hyperscale.command.core.model.Reachability
import com.hyperscale.command.ui.theme.LocalStatusColours

/** Maps a device class to an icon. Iconography is the fastest way to scan a long list. */
fun DeviceClass.icon(): ImageVector = when (this) {
    DeviceClass.LIGHT -> Icons.Filled.Lightbulb
    DeviceClass.SWITCH -> Icons.Outlined.ToggleOn
    DeviceClass.PLUG -> Icons.Outlined.Power
    DeviceClass.SENSOR -> Icons.Outlined.Sensors
    DeviceClass.THERMOSTAT -> Icons.Outlined.Thermostat
    DeviceClass.LOCK -> Icons.Outlined.Lock
    DeviceClass.CAMERA -> Icons.Outlined.Videocam
    DeviceClass.DOORBELL -> Icons.Outlined.Doorbell
    DeviceClass.SPEAKER -> Icons.Outlined.Speaker
    DeviceClass.TV -> Icons.Outlined.Tv
    DeviceClass.MEDIA -> Icons.Outlined.PlayCircle
    DeviceClass.APPLIANCE -> Icons.Outlined.Kitchen
    DeviceClass.VACUUM -> Icons.Outlined.CleaningServices
    DeviceClass.BLINDS -> Icons.Outlined.Blinds
    DeviceClass.FAN -> Icons.Outlined.Air
    DeviceClass.ENERGY -> Icons.Outlined.BatteryChargingFull
    DeviceClass.HUB -> Icons.Outlined.DeviceHub
    DeviceClass.NETWORK -> Icons.Outlined.Router
    DeviceClass.COMPUTER -> Icons.Outlined.Computer
    DeviceClass.PRINTER -> Icons.Outlined.Print
    DeviceClass.WEARABLE -> Icons.Outlined.Watch
    DeviceClass.VEHICLE -> Icons.Outlined.DirectionsCar
    DeviceClass.OTHER -> Icons.Outlined.DevicesOther
}

@Composable
fun DeviceStatus.colour(): Color {
    val status = LocalStatusColours.current
    return when (this) {
        DeviceStatus.ONLINE -> status.online
        DeviceStatus.RECENTLY_SEEN -> status.stale
        DeviceStatus.OFFLINE, DeviceStatus.UNREACHABLE -> status.offline
    }
}

@Composable
fun DeviceStatus.containerColour(): Color {
    val status = LocalStatusColours.current
    return when (this) {
        DeviceStatus.ONLINE -> status.onlineContainer
        DeviceStatus.RECENTLY_SEEN -> status.staleContainer
        DeviceStatus.OFFLINE, DeviceStatus.UNREACHABLE -> status.offlineContainer
    }
}

/** A small dot plus label. Reads as status at a glance without occupying a whole row. */
@Composable
fun StatusPill(
    status: DeviceStatus,
    modifier: Modifier = Modifier,
    showLabel: Boolean = true,
) {
    val colour by animateColorAsState(status.colour(), label = "statusColour")

    Row(
        modifier = modifier
            .clip(CircleShape)
            .background(status.containerColour())
            .padding(horizontal = if (showLabel) 10.dp else 6.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            modifier = Modifier
                .size(7.dp)
                .clip(CircleShape)
                .background(colour),
        )
        if (showLabel) {
            Text(
                text = status.label,
                style = MaterialTheme.typography.labelMedium,
                color = colour,
            )
        }
    }
}

/**
 * Protocol tag. Hub-bridged protocols get a distinct outline so it is immediately obvious which
 * devices are reachable only through Homey — that distinction drives what the user can do next.
 */
@Composable
fun ProtocolChip(
    protocol: Protocol,
    modifier: Modifier = Modifier,
    compact: Boolean = false,
) {
    val statusColours = LocalStatusColours.current
    val isBridged = protocol.reachability == Reachability.HUB_BRIDGED
    val accent = if (isBridged) statusColours.bridged else MaterialTheme.colorScheme.primary

    Row(
        modifier = modifier
            .clip(RoundedCornerShape(7.dp))
            .background(accent.copy(alpha = 0.12f))
            .border(
                width = 1.dp,
                color = accent.copy(alpha = if (isBridged) 0.55f else 0.28f),
                shape = RoundedCornerShape(7.dp),
            )
            .padding(horizontal = if (compact) 6.dp else 9.dp, vertical = if (compact) 2.dp else 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = protocol.displayName,
            style = MaterialTheme.typography.labelSmall,
            color = accent,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

/**
 * Signal strength rendered as four rising bars. RSSI is meaningless to most people as a number,
 * but bars are universally understood — the dBm value stays available in the detail pane.
 */
@Composable
fun SignalMeter(
    rssi: Int?,
    modifier: Modifier = Modifier,
) {
    if (rssi == null) return

    val bars = when {
        rssi >= -55 -> 4
        rssi >= -70 -> 3
        rssi >= -85 -> 2
        else -> 1
    }
    val accent = MaterialTheme.colorScheme.primary
    val dim = MaterialTheme.colorScheme.outlineVariant

    Row(
        modifier = modifier,
        verticalAlignment = Alignment.Bottom,
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        (1..4).forEach { index ->
            Box(
                modifier = Modifier
                    .width(3.dp)
                    .height((4 + index * 3).dp)
                    .clip(RoundedCornerShape(1.5.dp))
                    .background(if (index <= bars) accent else dim),
            )
        }
    }
}

@Composable
fun SectionHeader(
    title: String,
    modifier: Modifier = Modifier,
    trailing: String? = null,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = title.uppercase(),
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        trailing?.let {
            Text(
                text = it,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** Used wherever a list can legitimately be empty, which in a discovery app is often. */
@Composable
fun EmptyState(
    icon: ImageVector,
    title: String,
    body: String,
    modifier: Modifier = Modifier,
    action: (@Composable () -> Unit)? = null,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp, vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            modifier = Modifier
                .size(72.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surfaceContainerHigh),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(32.dp),
            )
        }
        Spacer(Modifier.height(4.dp))
        Text(
            text = title,
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onSurface,
        )
        Text(
            text = body,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.fillMaxWidth(),
        )
        action?.invoke()
    }
}

/** Consistent content padding so panes line up across screens on a large display. */
val PaneContentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp)
