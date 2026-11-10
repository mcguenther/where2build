import com.structurizr.Workspace;
import com.structurizr.dsl.StructurizrDslParser;
import com.structurizr.util.WorkspaceUtils;
import java.io.File;

/**
 * Parses a Structurizr DSL file with the reference parser and writes the
 * workspace as JSON -- the format Structurizr Lite, the cloud service and
 * scripts/architecture.mjs all read. Using the real parser means the DSL is
 * validated exactly as Structurizr itself would validate it.
 *
 *   java -cp "<jars>/*" scripts/architecture/DslToJson.java in.dsl out.json
 */
public class DslToJson {
    public static void main(String[] args) throws Exception {
        StructurizrDslParser parser = new StructurizrDslParser();
        parser.parse(new File(args[0]));
        Workspace workspace = parser.getWorkspace();
        WorkspaceUtils.saveWorkspaceToJson(workspace, new File(args[1]));
        System.out.println("views: " + workspace.getViews().getViews().size()
            + ", elements: " + workspace.getModel().getElements().size()
            + ", relationships: " + workspace.getModel().getRelationships().size());
    }
}
