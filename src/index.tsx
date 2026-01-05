import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  ToggleField,
  staticClasses,
} from "@decky/ui";
import {
  callable,
  definePlugin,
  toaster,
} from "@decky/api"
import { useCallback, useEffect, useState } from "react";
import { FaPlane } from "react-icons/fa";

type ServiceInfo = {
  unit: string;
  label: string;
  exists: boolean;
  active: boolean;
  enabled: boolean;
  canToggleEnable: boolean;
  activeState: string;
  subState: string;
  unitFileState: string;
  description?: string;
  loadState?: string;
};

const getServices = callable<[], ServiceInfo[]>("get_services");
const setServiceRunning = callable<[unit: string, running: boolean], ServiceInfo>("set_service_running");
const setServiceEnabled = callable<[unit: string, enabled: boolean], ServiceInfo>("set_service_enabled");

function Content() {
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [busyKeys, setBusyKeys] = useState<Record<string, boolean>>({});

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const next = await getServices();
      setServices(next);
    } catch (e) {
      console.error("Failed to load services", e);
      toaster.toast({
        title: "Tower Control",
        body: `Failed to load services: ${String(e)}`
      });
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const opKey = (unit: string, op: "running" | "enabled") => `${unit}::${op}`;

  const setBusy = (unit: string, op: "running" | "enabled", busy: boolean) => {
    const key = opKey(unit, op);
    setBusyKeys(prev => ({ ...prev, [key]: busy }));
  };

  const onToggleRunning = async (svc: ServiceInfo, running: boolean) => {
    setBusy(svc.unit, "running", true);
    try {
      const updated = await setServiceRunning(svc.unit, running);
      setServices(prev => prev.map(s => (s.unit === svc.unit ? { ...s, ...updated } : s)));
    } catch (e) {
      toaster.toast({
        title: "Tower Control",
        body: `Failed to ${running ? "start" : "stop"} ${svc.unit}: ${String(e)}`
      });
      // Re-sync state
      void refresh();
    } finally {
      setBusy(svc.unit, "running", false);
    }
  };

  const onToggleEnabled = async (svc: ServiceInfo, enabled: boolean) => {
    setBusy(svc.unit, "enabled", true);
    try {
      const updated = await setServiceEnabled(svc.unit, enabled);
      setServices(prev => prev.map(s => (s.unit === svc.unit ? { ...s, ...updated } : s)));
    } catch (e) {
      toaster.toast({
        title: "Tower Control",
        body: `Failed to ${enabled ? "enable" : "disable"} ${svc.unit}: ${String(e)}`
      });
      void refresh();
    } finally {
      setBusy(svc.unit, "enabled", false);
    }
  };

  return (
    <PanelSection title="Systemd services">
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() => refresh()}
          disabled={isRefreshing}
        >
          {isRefreshing ? "Refreshing…" : "Refresh"}
        </ButtonItem>
      </PanelSectionRow>

      {services.map((svc) => {
        const runningBusy = !!busyKeys[opKey(svc.unit, "running")];
        const enabledBusy = !!busyKeys[opKey(svc.unit, "enabled")];

        const runningDisabled = !svc.exists || runningBusy;
        const enabledDisabled = !svc.exists || enabledBusy || !svc.canToggleEnable;

        const runningDesc = svc.exists ? `${svc.unit} • ${svc.activeState}` : `${svc.unit} • not found`;
        const enabledDesc = svc.exists ? `UnitFileState: ${svc.unitFileState}` : "Unit not found";

        return (
          <div key={svc.unit}>
            <PanelSectionRow>
              <ToggleField
                label={svc.label}
                description={runningDesc}
                checked={!!svc.active}
                disabled={runningDisabled}
                onChange={(checked: boolean) => onToggleRunning(svc, checked)}
              />
            </PanelSectionRow>

            <PanelSectionRow>
              <div style={{ paddingLeft: 16 }}>
                <ToggleField
                  label="Start on boot"
                  description={enabledDesc}
                  checked={!!svc.enabled}
                  disabled={enabledDisabled}
                  onChange={(checked: boolean) => onToggleEnabled(svc, checked)}
                />
              </div>
            </PanelSectionRow>
          </div>
        );
      })}
    </PanelSection>
  );
};

export default definePlugin(() => {
  console.log("Tower Control initializing")

  return {
    // The name shown in various decky menus
    name: "Tower Control",
    // The element displayed at the top of your plugin's menu
    titleView: <div className={staticClasses.Title}>Tower Control</div>,
    // The content of your plugin's menu
    content: <Content />,
    // The icon displayed in the plugin list
    icon: <FaPlane />,
    // The function triggered when your plugin unloads
    onDismount() {
      console.log("Tower Control unloading")
    },
  };
});
