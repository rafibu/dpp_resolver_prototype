import {Component, computed, inject} from '@angular/core';
import {CommonModule} from '@angular/common';
import {Edge, NgxGraphModule, Node} from '@swimlane/ngx-graph';
import {FederationService} from '../../core/federation.service';
import {PlatformStatus} from '../../core/models/federation.model';
import {Router} from '@angular/router';

@Component({
  selector: 'app-federation-map',
  standalone: true,
  imports: [CommonModule, NgxGraphModule],
  templateUrl: './federation-map.component.html',
  styleUrl: './federation-map.component.scss'
})
export class FederationMapComponent {
  private federationService = inject(FederationService);
  private router = inject(Router);

  public nodes = computed<Node[]>(() => {
    const federation = this.federationService.federation();
    if (!federation) return [];

    const nodes: Node[] = [];

    // Resolver node
    if (federation.resolver) {
      nodes.push({
        id: 'resolver',
        label: 'Resolver',
        data: {
          type: 'resolver',
          url: federation.resolver.external_url,
          status: federation.resolver.status
        }
      });
    }

    // Platform nodes
    federation.platforms.forEach(platform => {
      nodes.push({
        id: platform.platform_id,
        label: platform.platform_id,
        data: {
          type: 'platform',
          issuer: platform.issuer_id,
          subjectTypes: platform.subject_types,
          status: platform.status,
          url: platform.external_url
        }
      });
    });

    return nodes;
  });

  public links = computed<Edge[]>(() => {
    const federation = this.federationService.federation();
    if (!federation || !federation.resolver) return [];

    return federation.platforms.map(platform => ({
      id: `edge-${platform.platform_id}`,
      source: platform.platform_id,
      target: 'resolver',
      label: 'resolves'
    }));
  });

  public getStatusColor(status: PlatformStatus): string {
    switch (status) {
      case PlatformStatus.RUNNING:
        return '#27ae60';
      case PlatformStatus.PAUSED:
        return '#7f8c8d';
      case PlatformStatus.ERROR:
        return '#e74c3c';
      case PlatformStatus.STARTING:
        return '#f39c12';
      default:
        return '#bdc3c7';
    }
  }

  public onNodeClick(node: Node): void {
    if (node.data.type === 'platform') {
      void this.router.navigate(['/platforms', node.id]);
    }
  }
}
