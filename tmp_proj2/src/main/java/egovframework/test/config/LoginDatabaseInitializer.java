package egovframework.test.config;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.util.StreamUtils;

@Configuration
public class LoginDatabaseInitializer {

    private static final Pattern ALTER_ADD_COLUMN_PATTERN = Pattern.compile(
            "(?is)^\\s*ALTER\\s+TABLE\\s+[`\\"]?([A-Za-z0-9_.$-]+)[`\\"]?\\s+ADD\\s+(?:COLUMN\\s+)?[`\\"]?([A-Za-z0-9_.$-]+)[`\\"]?.*$");

    @Bean
    public ApplicationRunner loginDatabaseInitializerRunner(DataSource dataSource) {
        return args -> {
            List<Resource> resources = new ArrayList<>();
            for (String resourceName : new String[] {"schema.sql", "data.sql", "login-schema.sql", "login-data.sql"}) {
                ClassPathResource resource = new ClassPathResource(resourceName);
                if (resource.exists()) {
                    resources.add(resource);
                }
            }
            if (resources.isEmpty()) {
                return;
            }
            try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
                for (Resource resource : resources) {
                    executeResource(connection, statement, resource);
                }
            }
        };
    }

    private void executeResource(Connection connection, Statement statement, Resource resource) throws IOException, SQLException {
        String sql = StreamUtils.copyToString(resource.getInputStream(), StandardCharsets.UTF_8);
        for (String raw : splitStatements(sql)) {
            String stmt = raw == null ? "" : raw.trim();
            if (stmt.isEmpty()) {
                continue;
            }
            if (shouldSkipStatement(connection, stmt)) {
                continue;
            }
            statement.execute(stmt);
        }
    }

    private boolean shouldSkipStatement(Connection connection, String statement) throws SQLException {
        Matcher matcher = ALTER_ADD_COLUMN_PATTERN.matcher(statement);
        if (!matcher.matches()) {
            return false;
        }
        String tableName = unquoteIdentifier(matcher.group(1));
        String columnName = unquoteIdentifier(matcher.group(2));
        return columnExists(connection, tableName, columnName);
    }

    private boolean columnExists(Connection connection, String tableName, String columnName) throws SQLException {
        DatabaseMetaData metaData = connection.getMetaData();
        String normalizedTable = normalizeLookupName(tableName, metaData.storesLowerCaseIdentifiers(), metaData.storesUpperCaseIdentifiers());
        String normalizedColumn = normalizeLookupName(columnName, metaData.storesLowerCaseIdentifiers(), metaData.storesUpperCaseIdentifiers());
        String schema = connection.getSchema();
        String catalog = connection.getCatalog();
        for (String schemaCandidate : schemaCandidates(schema, null)) {
            if (matchesColumn(metaData, catalog, schemaCandidate, normalizedTable, normalizedColumn)) {
                return true;
            }
            if (matchesColumn(metaData, null, schemaCandidate, normalizedTable, normalizedColumn)) {
                return true;
            }
        }
        for (String catalogCandidate : schemaCandidates(catalog, null)) {
            if (matchesColumn(metaData, catalogCandidate, schema, normalizedTable, normalizedColumn)) {
                return true;
            }
            if (matchesColumn(metaData, catalogCandidate, null, normalizedTable, normalizedColumn)) {
                return true;
            }
        }
        return matchesColumn(metaData, null, null, normalizedTable, normalizedColumn);
    }

    private boolean matchesColumn(DatabaseMetaData metaData, String catalog, String schema, String table, String column) throws SQLException {
        try (ResultSet rs = metaData.getColumns(catalog, schema, table, column)) {
            return rs.next();
        }
    }

    private List<String> schemaCandidates(String primary, String secondary) {
        List<String> values = new ArrayList<>();
        if (primary != null && !primary.isBlank()) {
            values.add(primary);
        }
        if (secondary != null && !secondary.isBlank() && !values.contains(secondary)) {
            values.add(secondary);
        }
        values.add(null);
        return values;
    }

    private String normalizeLookupName(String value, boolean lower, boolean upper) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        if (trimmed.isEmpty()) {
            return trimmed;
        }
        if (lower) {
            return trimmed.toLowerCase(Locale.ROOT);
        }
        if (upper) {
            return trimmed.toUpperCase(Locale.ROOT);
        }
        return trimmed;
    }

    private String unquoteIdentifier(String value) {
        if (value == null) {
            return "";
        }
        return value.replace("`", "").replace("\\"", "").trim();
    }

    private List<String> splitStatements(String sql) {
        List<String> statements = new ArrayList<>();
        if (sql == null || sql.isBlank()) {
            return statements;
        }
        StringBuilder current = new StringBuilder();
        boolean singleQuoted = false;
        boolean doubleQuoted = false;
        boolean lineComment = false;
        boolean blockComment = false;
        for (int i = 0; i < sql.length(); i++) {
            char ch = sql.charAt(i);
            char next = i + 1 < sql.length() ? sql.charAt(i + 1) : '\\0';
            if (lineComment) {
                if (ch == '\\n') {
                    lineComment = false;
                }
                continue;
            }
            if (blockComment) {
                if (ch == '*' && next == '/') {
                    blockComment = false;
                    i++;
                }
                continue;
            }
            if (!singleQuoted && !doubleQuoted) {
                if (ch == '-' && next == '-') {
                    lineComment = true;
                    i++;
                    continue;
                }
                if (ch == '/' && next == '*') {
                    blockComment = true;
                    i++;
                    continue;
                }
            }
            if (ch == '\\'' && !doubleQuoted) {
                singleQuoted = !singleQuoted;
                current.append(ch);
                continue;
            }
            if (ch == '"' && !singleQuoted) {
                doubleQuoted = !doubleQuoted;
                current.append(ch);
                continue;
            }
            if (ch == ';' && !singleQuoted && !doubleQuoted) {
                String stmt = current.toString().trim();
                if (!stmt.isEmpty()) {
                    statements.add(stmt);
                }
                current.setLength(0);
                continue;
            }
            current.append(ch);
        }
        String tail = current.toString().trim();
        if (!tail.isEmpty()) {
            statements.add(tail);
        }
        return statements;
    }
}
