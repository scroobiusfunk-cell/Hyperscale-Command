package com.hyperscale.command.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.hyperscale.command.core.model.Device
import com.hyperscale.command.core.model.DeviceStatus
import com.hyperscale.command.ui.theme.LocalStatusColours

/**
 * One row in the device list.
 *
 * Priorities, in order: is it on, what is it, where is it, how do I reach it. The on/off switch
 * sits on the right where a thumb naturally lands, and only appears for devices that can actually
 * be controlled — showing a dead switch on an unreachable device is worse than showing none.
 */
@Composable
fun DeviceCard(
    device: Device,
    selected: Boolean,
    onClick: () -> Unit,
    onToggle: ((Boolean) -> Unit)?,
    onFavourite: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val statusColours = LocalStatusColours.current
    val isOffline = device.status == DeviceStatus.OFFLINE || device.status == DeviceStatus.UNREACHABLE

    val borderColour by animateColorAsState(
        targetValue = when {
            selected -> MaterialTheme.colorScheme.primary
            device.isOn == true -> statusColours.controllable.copy(alpha = 0.4f)
            else -> MaterialTheme.colorScheme.outlineVariant
        },
        label = "cardBorder",
    )

    val contentAlpha by animateFloatAsState(
        targetValue = if (isOffline) 0.55f else 1f,
        label = "cardAlpha",
    )

    Card(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .semantics {
                contentDescription = buildString {
                    append(device.displayName)
                    append(", ").append(device.deviceClass.label)
                    append(", ").append(device.status.label)
                    device.isOn?.let { append(if (it) ", on" else ", off") }
                }
            },
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) {
                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.35f)
            } else {
                MaterialTheme.colorScheme.surfaceContainer
            },
        ),
        border = androidx.compose.foundation.BorderStroke(
            width = if (selected) 1.5.dp else 1.dp,
            color = borderColour,
        ),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(14.dp)
                .alpha(contentAlpha),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            DeviceGlyph(device = device)

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(
                        text = device.displayName,
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    if (device.isFavourite) {
                        Icon(
                            imageVector = Icons.Filled.Star,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.tertiary,
                            modifier = Modifier.size(14.dp),
                        )
                    }
                }

                Spacer(Modifier.size(3.dp))

                Text(
                    text = device.subtitle,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )

                Spacer(Modifier.size(8.dp))

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    StatusPill(status = device.status, showLabel = false)
                    device.protocols.take(2).forEach { protocol ->
                        ProtocolChip(protocol = protocol, compact = true)
                    }
                    if (device.protocols.size > 2) {
                        Text(
                            text = "+${device.protocols.size - 2}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Spacer(Modifier.weight(1f))
                    SignalMeter(rssi = device.rssi)
                }
            }

            when {
                onToggle != null && device.isOn != null -> {
                    Switch(
                        checked = device.isOn == true,
                        onCheckedChange = onToggle,
                        colors = SwitchDefaults.colors(
                            checkedTrackColor = statusColours.controllable,
                            checkedThumbColor = MaterialTheme.colorScheme.surface,
                        ),
                    )
                }

                else -> {
                    IconButton(onClick = onFavourite) {
                        Icon(
                            imageVector = if (device.isFavourite) Icons.Filled.Star else Icons.Outlined.StarBorder,
                            contentDescription = if (device.isFavourite) {
                                "Remove ${device.displayName} from favourites"
                            } else {
                                "Add ${device.displayName} to favourites"
                            },
                            tint = if (device.isFavourite) {
                                MaterialTheme.colorScheme.tertiary
                            } else {
                                MaterialTheme.colorScheme.onSurfaceVariant
                            },
                        )
                    }
                }
            }
        }
    }
}

/**
 * The circular device badge. Fills with the accent colour when a light or switch is on, which
 * makes "what is currently on in my house" answerable by scrolling rather than reading.
 */
@Composable
private fun DeviceGlyph(device: Device) {
    val statusColours = LocalStatusColours.current
    val isOn = device.isOn == true

    val background by animateColorAsState(
        targetValue = if (isOn) {
            statusColours.controllable.copy(alpha = 0.22f)
        } else {
            MaterialTheme.colorScheme.surfaceContainerHighest
        },
        label = "glyphBackground",
    )

    val tint by animateColorAsState(
        targetValue = if (isOn) statusColours.controllable else MaterialTheme.colorScheme.onSurfaceVariant,
        label = "glyphTint",
    )

    Box(
        modifier = Modifier
            .size(46.dp)
            .clip(CircleShape)
            .background(background)
            .border(
                width = 1.dp,
                color = if (isOn) statusColours.controllable.copy(alpha = 0.5f) else androidx.compose.ui.graphics.Color.Transparent,
                shape = CircleShape,
            ),
        contentAlignment = Alignment.Center,
    ) {
        Icon(
            imageVector = device.deviceClass.icon(),
            contentDescription = null,
            tint = tint,
            modifier = Modifier.size(22.dp),
        )
    }
}

/** Compact variant used inside the Homey zone grid, where space is at a premium. */
@Composable
fun DeviceChipCard(
    device: Device,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        onClick = onClick,
        modifier = modifier.width(168.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainer,
        ),
    ) {
        Column(
            modifier = Modifier.padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DeviceGlyph(device = device)
            Text(
                text = device.displayName,
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            Text(
                text = device.homeyZoneName ?: device.primaryProtocol.displayName,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}
